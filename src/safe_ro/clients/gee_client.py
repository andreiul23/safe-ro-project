import ee
import numpy as np
import requests
import io
import rasterio


class GEEClient:
    def __init__(self, project=None):
        try:
            ee.Initialize(project=project)
        except Exception as e:
            # If already initialized or other error, check for specific messages
            if "Already initialized" not in str(e):
                print(f"GEE Initialization Error: {e}")
                raise  # Re-raise if it's an unexpected error

    def _mask_s2_clouds(self, image):
        """Masks clouds in a Sentinel-2 image using the QA60 band."""
        qa = image.select("QA60")
        # Bits 10 and 11 are clouds and cirrus, respectively.
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        # Both flags should be set to zero, indicating clear conditions.
        mask = (
            qa.bitwiseAnd(cloud_bit_mask)
            .eq(0)
            .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        )
        return image.updateMask(mask).divide(10000)  # Scale to reflectance

    def _scale_s2_bands(self, image):
        """Scales Sentinel-2 bands to reflectance [0, 1]."""
        # Already handled by _mask_s2_clouds due to division by 10000
        # This function might be redundant if _mask_s2_clouds handles scaling.
        # But if we decide to separate cloud masking from scaling, this would be useful.
        # For now, we'll keep the scaling within _mask_s2_clouds
        return image

    def get_ndvi(self, aoi, start_date, end_date):
        """
        Retrieves Sentinel-2 data, computes NDVI, and returns it as a NumPy array
        along with its bounds.
        """
        try:
            # Load Sentinel-2 Surface Reflectance data.
            s2_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterDate(start_date, end_date)
                .filterBounds(aoi)
            )

            # Apply cloud mask and scale bands.
            s2_collection = s2_collection.map(self._mask_s2_clouds)

            # Filter for images with valid bands
            s2_collection = s2_collection.select(
                "B4", "B8", "B3"
            )  # Red, NIR, Green for visualization if needed

            if s2_collection.size().getInfo() == 0:
                msg = f"GEEClient: No Sentinel-2 images found for the selected region and dates."
                print(msg)
                return None, None, msg

            # Get the median image from the collection.
            median_image = s2_collection.median()

            # Compute NDVI.
            ndvi = median_image.normalizedDifference(["B8", "B4"]).rename("NDVI")

            # --- Convert ee.Image to NumPy Array and get bounds ---
            projection = ndvi.projection().getInfo()
            crs = projection["crs"]
            region_geojson = aoi.getInfo()
            nominal_scale = ndvi.projection().nominalScale().getInfo()

            download_args = {
                "name": "ndvi_data",
                "crs": crs,
                "scale": nominal_scale,
                "region": region_geojson,
                "fileFormat": "GeoTIFF",
                "format": "GEO_TIFF",
            }

            download_url = ndvi.getDownloadUrl(download_args)
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with rasterio.open(io.BytesIO(response.content)) as src:
                ndvi_array = src.read(1)
                bounds = src.bounds
                gee_bounds_format = [
                    bounds.left,
                    bounds.bottom,
                    bounds.right,
                    bounds.top,
                ]

            if src.nodata is not None:
                ndvi_array[ndvi_array == src.nodata] = np.nan

            return ndvi_array, gee_bounds_format, None

        except ee.EEException as e:
            msg = f"A Google Earth Engine error occurred during NDVI analysis: {e}"
            print(msg)
            return None, None, msg
        except requests.exceptions.RequestException as e:
            msg = f"A network error occurred while downloading NDVI data: {e}"
            print(msg)
            return None, None, msg
        except rasterio.errors.RasterioIOError as e:
            msg = f"An error occurred reading the downloaded NDVI data: {e}"
            print(msg)
            return None, None, msg
        except Exception as e:
            msg = f"An unexpected error occurred in get_ndvi: {e}"
            print(msg)
            return None, None, msg

    def get_flood_data(self, aoi, start_date, end_date):
        """
        Retrieves Sentinel-1 data, applies flood detection (thresholding),
        and returns it as a NumPy array along with its bounds.
        """
        try:
            # Step 1: Load collection
            try:
                s1_collection = (
                    ee.ImageCollection("COPERNICUS/S1_GRD")
                    .filterDate(start_date, end_date)
                    .filterBounds(aoi)
                    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                    .filter(ee.Filter.eq("instrumentMode", "IW"))
                    .select("VV")
                )

                if s1_collection.size().getInfo() == 0:
                    return None, None, "No Sentinel-1 images found for the selected criteria."
            except Exception as e:
                return None, None, f"Failed during data loading: {e}"

            # Step 2: Pre-processing
            try:
                median_s1 = s1_collection.median()
                nominal_scale = median_s1.projection().nominalScale().getInfo()
                filtered_s1 = median_s1.focal_median(3, "square", "pixels")
            except Exception as e:
                return None, None, f"Failed during pre-processing (median/speckle filter): {e}"

            # Step 3: Percentile Thresholding
            try:
                # Calculate the 15th percentile of pixel values in the region.
                water_threshold_reducer = ee.Reducer.percentile([15])
                water_threshold_dict = filtered_s1.reduceRegion(
                    reducer=water_threshold_reducer,
                    geometry=aoi,
                    scale=nominal_scale,
                    bestEffort=True
                )
                water_threshold_number = water_threshold_dict.get('VV')

                # Explicitly convert the threshold number to an image for comparison.
                threshold_img = ee.Image.constant(water_threshold_number)
                flood_map = filtered_s1.lt(threshold_img).rename("Flood")
            except Exception as e:
                return None, None, f"Failed during percentile thresholding: {e}"

            # Step 4: Water Masking
            try:
                gsw = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
                permanent_water = gsw.select("occurrence").gt(30)
                temp_flood = flood_map.And(permanent_water.Not()).selfMask()
            except Exception as e:
                return None, None, f"Failed during permanent water masking: {e}"

            # Step 5: Prepare for download
            try:
                projection = temp_flood.projection().getInfo()
                crs = projection["crs"]
                region_geojson = aoi.getInfo()

                download_args = {
                    "name": "flood_data",
                    "crs": crs,
                    "scale": nominal_scale,
                    "region": region_geojson,
                    "fileFormat": "GeoTIFF",
                    "format": "GEO_TIFF",
                }
                download_url = temp_flood.getDownloadUrl(download_args)
            except Exception as e:
                return None, None, f"Failed while preparing download URL: {e}"

            # Step 6: Download and Read
            try:
                response = requests.get(download_url, stream=True)
                response.raise_for_status()
                with rasterio.open(io.BytesIO(response.content)) as src:
                    flood_array = src.read(1).astype(float)
                    bounds = src.bounds
                    gee_bounds_format = [
                        bounds.left,
                        bounds.bottom,
                        bounds.right,
                        bounds.top,
                    ]
                    if src.nodata is not None:
                        flood_array[flood_array == src.nodata] = np.nan
                return flood_array, gee_bounds_format, None
            except requests.exceptions.RequestException as e:
                return None, None, f"Network error during download: {e}"
            except rasterio.errors.RasterioIOError as e:
                return None, None, f"Error reading downloaded file: {e}"
            except Exception as e:
                return None, None, f"Failed during download/read phase: {e}"

        except Exception as e:
            # Fallback for any other unexpected error
            return None, None, f"An unexpected error occurred in get_flood_data: {e}"