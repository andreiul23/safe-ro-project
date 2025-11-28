from safe_ro_core import RasterBand, NDVIProcessor, Sentinel1FloodDetector

# Test 1: Load a raster band
band = RasterBand("example.tif")   # put ANY .tif path here
band.load()
print("Band loaded successfully")

# Test 2: NDVI
ndvi = NDVIProcessor("red_band.tif", "nir_band.tif")
print("NDVI:", ndvi.compute_ndvi())

# Test 3: Flood detection
flood = Sentinel1FloodDetector("s1_vv.tif")
mask = flood.detect()
print("Flooded %:", (mask.mean() * 100))
