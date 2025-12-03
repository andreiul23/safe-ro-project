import numpy as np
import rasterio
from rasterio.enums import Resampling
import cv2

class RasterBand:
    def __init__(self, path: str):
        self.path = path
        self.data = None

    def load(self, downsample_factor=1):
        try:
            with rasterio.open(self.path) as src:
                new_h = src.height // downsample_factor
                new_w = src.width // downsample_factor
                self.data = src.read(
                    1,
                    out_shape=(new_h, new_w) if new_h > 0 and new_w > 0 else None,
                    resampling=Resampling.bilinear
                ).astype(np.float32)
        except Exception as e:
            print(f"[ERROR] Failed to load {self.path}: {e}")
            self.data = None
        return self.data

class NDVIProcessor:
    def __init__(self, red_path: str, nir_path: str):
        self.red_band = RasterBand(red_path)
        self.nir_band = RasterBand(nir_path)

    def compute_ndvi(self):
        red = self.red_band.load()
        nir = self.nir_band.load()

        if red is None or nir is None: return None, None

        if red.shape != nir.shape:
            target_shape = (max(red.shape[0], nir.shape[0]), max(red.shape[1], nir.shape[1]))
            red = cv2.resize(red, (target_shape[1], target_shape[0]))
            nir = cv2.resize(nir, (target_shape[1], target_shape[0]))

        denom = nir + red
        denom[denom == 0] = 1e-6  # Avoid division by zero
        ndvi = (nir - red) / denom
        
        with rasterio.open(self.red_band.path) as src:
            bounds = src.bounds

        return np.clip(ndvi, -1.0, 1.0), bounds

class Sentinel1FloodDetector:
    def __init__(self, path: str):
        self.band = RasterBand(path)

    def detect(self, threshold=None, percentile=20.0):
        data = self.band.load()
        if data is None: return None, None
        
        # If no explicit threshold is given, calculate one using the percentile
        if threshold is None:
            threshold = np.percentile(data, percentile)
        
        with rasterio.open(self.band.path) as src:
            bounds = src.bounds
            
        return (data < threshold).astype(np.uint8), bounds