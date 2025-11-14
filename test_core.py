from safe_ro_core import RasterBand, NDVIProcessor, Sentinel1FloodDetector, FireDetector

# Test 1: Load a raster band
band = RasterBand("example.tif")   # put ANY .tif path here
band.load()
print("Stats:", band.stats())

# Test 2: NDVI
ndvi = NDVIProcessor("red_band.tif", "nir_band.tif")
ndvi.load()
print("NDVI:", ndvi.compute_ndvi())

# Test 3: Flood detection
flood = Sentinel1FloodDetector("s1_vv.tif")
mask = flood.detect()
print("Flooded %:", (mask.mean() * 100))

# Test 4: Fire CSV
fires = FireDetector("fires.csv")
fires.load()
print("High confidence fires:", len(fires.filter_by_confidence(80)))
