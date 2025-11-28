import numpy as np
import rasterio
from rasterio.enums import Resampling
import pandas as pd
import cv2

class RasterBand:
    def __init__(self, path: str):
        self.path = path
        self.data = None

    def load(self, downsample_factor=2):
        try:
            with rasterio.open(self.path) as src:
                new_h = src.height // downsample_factor
                new_w = src.width // downsample_factor
                self.data = src.read(
                    1,
                    out_shape=(new_h, new_w),
                    resampling=Resampling.bilinear
                ).astype(np.float32)
        except Exception as e:
            print("[ERROR]", e)
            self.data = None

class NDVIProcessor:
    def __init__(self, red_path: str, nir_path: str):
        self.red_band = RasterBand(red_path)
        self.nir_band = RasterBand(nir_path)

    def compute_ndvi(self):
        # 1. Load
        self.red_band.load(downsample_factor=2)
        self.nir_band.load(downsample_factor=2)
        red = self.red_band.data
        nir = self.nir_band.data

        if red is None or nir is None: return None

        # 2. Resize Match
        if red.shape != nir.shape:
            target_shape = max(red.shape, nir.shape)
            if red.shape != target_shape:
                red = cv2.resize(red, (target_shape[1], target_shape[0]))
            if nir.shape != target_shape:
                nir = cv2.resize(nir, (target_shape[1], target_shape[0]))

        # 3. Compute NDVI (No Masking - Show Everything)
        denom = (nir + red)
        denom[denom == 0] = 0.0001
        ndvi = (nir - red) / denom
        
        return np.clip(ndvi, -1.0, 1.0)

class Sentinel1FloodDetector:
    def __init__(self, path: str):
        self.band = RasterBand(path)

    def detect(self, percentile=20.0):
        self.band.load(downsample_factor=2)
        if self.band.data is None: return None
        thresh = np.percentile(self.band.data, percentile)
        return self.band.data < thresh