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
                raise # Re-raise if it's an unexpected error

    def _mask_s2_clouds(self, image):
        """Masks clouds in a Sentinel-2 image using the QA60 band."""
        qa = image.select('QA60')
        # Bits 10 and 11 are clouds and cirrus, respectively.
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        # Both flags should be set to zero, indicating clear conditions.
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
               qa.bitwiseAnd(cirrus_bit_mask).eq(0))
        return image.updateMask(mask).divide(10000) # Scale to reflectance

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
            s2_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
                .filterDate(start_date, end_date) \
                .filterBounds(aoi)

            # Apply cloud mask and scale bands.
            s2_collection = s2_collection.map(self._mask_s2_clouds)

            # Filter for images with valid bands
            s2_collection = s2_collection.select('B4', 'B8', 'B3') # Red, NIR, Green for visualization if needed

            if s2_collection.size().getInfo() == 0:
                print(f"GEEClient: No Sentinel-2 images found for AOI: {aoi}, dates: {start_date} to {end_date}")
                return None, None

            # Get the median image from the collection.
            median_image = s2_collection.median()

            # Compute NDVI.
            ndvi = median_image.normalizedDifference(['B8', 'B4']).rename('NDVI')

            # --- Convert ee.Image to NumPy Array and get bounds ---
            # Get the projection of the image.
            # Use the default projection of the image for resampling
            projection = ndvi.projection().getInfo()
            crs = projection['crs']
            transform = projection['transform']

            # Get the image bounds in the CRS of the image itself
            # This is important for requesting pixels in the correct coordinate system.
            aoi_bounds = aoi.bounds().transform(crs, 0.01).getInfo()
            
            # Request pixels. This fetches the image data as a GeoTIFF byte stream.
            # Set a default scale (e.g., 10 meters for Sentinel-2)
            scale = 10
            
            # It's better to explicitly define the region for getPixels
            region_geojson = aoi.getInfo()['geometry']
            
            params = {
                'crs': crs,
                'bands': ['NDVI'],
                'min': -1, 'max': 1, # NDVI range
                'dimensions': '512x512', # Request a reasonable size
                'region': region_geojson,
                'format': 'NPY' # Use NPY format for direct numpy array
            }
            
            # The getPixels method does not return a numpy array directly for the Python client.
            # It returns a JSON object with metadata or starts a process.
            # To get a numpy array, we need to use getThumbUrl or getDownloadUrl and process a GeoTIFF
            # or use image.sampleRegions().
            # Given the requirement for a numpy array for direct use, downloading a GeoTIFF is the most robust.
            # Let's try to get a thumbnail if the region is small for direct visualization.
            # For exact data, download or sampleRegions is needed.

            # Option 1: Get data as a thumbnail (less precise but good for visualization)
            # This returns an image, not raw data and bounds.

            # Option 2: Using ee.data.getDownloadId and then requests to download GeoTIFF
            # This is more robust for actual data retrieval.
            
            # Let's try to use getDownloadUrl and then rasterio to read it.
            # This approach is more reliable for getting raster data.

            # Define export parameters.
            # Request the original scale of the image for accuracy.
            nominal_scale = ndvi.projection().nominalScale().getInfo()

            download_args = {
                'name': 'ndvi_data',
                'crs': crs,
                'scale': nominal_scale,
                'region': region_geojson,
                'fileFormat': 'GeoTIFF',
                'format': 'GEO_TIFF'
            }

            download_url = ndvi.getDownloadUrl(download_args)
            
            # Download the GeoTIFF
            response = requests.get(download_url, stream=True)
            response.raise_for_status() # Raise an exception for HTTP errors
            
            # Read the GeoTIFF into a numpy array using rasterio
            with rasterio.open(io.BytesIO(response.content)) as src:
                ndvi_array = src.read(1) # Read the first band
                bounds = src.bounds
                # rasterio bounds are (left, bottom, right, top)
                # Convert to GEE-like format [min_lon, min_lat, max_lon, max_lat]
                gee_bounds_format = [bounds.left, bounds.bottom, bounds.right, bounds.top]

            # Replace no-data values with NaN for consistent processing in main_app
            ndvi_array[ndvi_array == src.nodata] = np.nan

            return ndvi_array, gee_bounds_format

        except ee.EEException as e:
            print(f"GEE Error in get_ndvi: {e}")
            return None, None
        except requests.exceptions.RequestException as e:
            print(f"HTTP Error downloading GeoTIFF in get_ndvi: {e}")
            return None, None
        except rasterio.errors.RasterioIOError as e:
            print(f"Rasterio IO Error reading GeoTIFF in get_ndvi: {e}")
            return None, None
        except Exception as e:
            print(f"An unexpected error occurred in get_ndvi: {e}")
            return None, None

    def get_flood_data(self, aoi, start_date, end_date):
        """
        Retrieves Sentinel-1 data, applies flood detection (thresholding),
        and returns it as a NumPy array along with its bounds.
        """
        try:
            # Load Sentinel-1 GRD data.
            s1_collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
                .filterDate(start_date, end_date) \
                .filterBounds(aoi) \
                .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
                .filter(ee.Filter.eq('instrumentMode', 'IW')) \
                .select('VV')

            if s1_collection.size().getInfo() == 0:
                print(f"GEEClient: No Sentinel-1 images found for AOI: {aoi}, dates: {start_date} to {end_date}")
                return None, None

            # Get the median image from the collection.
            median_s1 = s1_collection.median()

            # Apply speckle filter (e.g., median filter)
            # kernel_size = 5 # Use an odd number
            # filtered_s1 = median_s1.focal_median(kernel_size, 'square', 'pixels')
            # For simplicity, let's skip speckle filter for now, or use a simpler one
            # Convert to decibels (already often done for GRD, but good to ensure)
            # S1 GRD images are already in linear scale (power), so convert to dB
            s1_db = ee.Image(median_s1).log10().multiply(10.0)

            # Define a threshold for water detection. Water has low backscatter.
            # Common range for flood detection is -18 dB to -22 dB. Let's use -20 dB.
            water_threshold = -20 # dB

            # Create a binary flood map (1 = water, 0 = land)
            # Areas below the threshold are classified as water.
            flood_map = s1_db.lt(water_threshold).rename('Flood')

            # --- Mask permanent water bodies using JRC Global Surface Water ---
            # Load JRC Global Surface Water (GSW) data, permanent water mask.
            # The 'occurrence' band for water occurrence (0-100%).
            # We want to mask out areas with high water occurrence (e.g., > 10%)
            # to focus on temporary floods.
            gsw = ee.Image('JRC/GSW1_4/GlobalSurfaceWater')
            permanent_water = gsw.select('occurrence').gt(10) # 10% occurrence threshold for permanent water

            # Remove permanent water from the flood map.
            # Only consider flood pixels that are NOT permanent water.
            temp_flood = flood_map.And(permanent_water.Not())

            # --- Convert ee.Image to NumPy Array and get bounds ---
            # Get the projection of the image.
            projection = temp_flood.projection().getInfo()
            crs = projection['crs']
            transform = projection['transform']

            region_geojson = aoi.getInfo()['geometry']
            
            # Define export parameters.
            nominal_scale = temp_flood.projection().nominalScale().getInfo()

            download_args = {
                'name': 'flood_data',
                'crs': crs,
                'scale': nominal_scale,
                'region': region_geojson,
                'fileFormat': 'GeoTIFF',
                'format': 'GEO_TIFF'
            }

            download_url = temp_flood.getDownloadUrl(download_args)
            
            # Download the GeoTIFF
            response = requests.get(download_url, stream=True)
            response.raise_for_status() # Raise an exception for HTTP errors
            
            # Read the GeoTIFF into a numpy array using rasterio
            with rasterio.open(io.BytesIO(response.content)) as src:
                flood_array = src.read(1) # Read the first band
                bounds = src.bounds
                # Convert to GEE-like format [min_lon, min_lat, max_lon, max_lat]
                gee_bounds_format = [bounds.left, bounds.bottom, bounds.right, bounds.top]

            # Replace no-data values with NaN for consistent processing in main_app
            flood_array[flood_array == src.nodata] = np.nan
            
            return flood_array, gee_bounds_format

        except ee.EEException as e:
            print(f"GEE Error in get_flood_data: {e}")
            return None, None
        except requests.exceptions.RequestException as e:
            print(f"HTTP Error downloading GeoTIFF in get_flood_data: {e}")
            return None, None
        except rasterio.errors.RasterioIOError as e:
            print(f"Rasterio IO Error reading GeoTIFF in get_flood_data: {e}")
            return None, None
        except Exception as e:
            print(f"An unexpected error occurred in get_flood_data: {e}")
            return None, None
