"""
SAFE-RO core module

Features:
- Generic raster loader
- NDVI from Sentinel/Landsat bands
- Flood detection from Sentinel-1
- Fire processing from FIRMS CSV
- Copernicus (Sentinel) downloader via sentinelsat
- A simple end-to-end pipeline wrapper
"""

import numpy as np
import rasterio
import matplotlib.pyplot as plt
import pandas as pd

# Optional – only needed for automatic Sentinel downloads
try:
    from sentinelsat import SentinelAPI, geojson_to_wkt
except ImportError:
    SentinelAPI = None
    geojson_to_wkt = None
    print("[WARN] sentinelsat not installed. CopernicusDownloader will not work.")


# ─────────────────────────────────────────────────────────────────────────────
# Base raster class
# ─────────────────────────────────────────────────────────────────────────────

class RasterBand:
    """Generic raster band loader + basic stats and visualization."""

    def __init__(self, path: str):
        self.path = path
        self.dataset = None
        self.data = None  # 2D array

    def load(self):
        try:
            self.dataset = rasterio.open(self.path)
            self.data = self.dataset.read(1).astype(float)
            print(f"[INFO] Loaded raster: {self.path}")
        except Exception as e:
            print("[ERROR] Could not load raster:", e)

    def stats(self):
        if self.data is None:
            print("[WARN] No data loaded.")
            return None

        return {
            "min": float(np.nanmin(self.data)),
            "max": float(np.nanmax(self.data)),
            "mean": float(np.nanmean(self.data)),
            "std": float(np.nanstd(self.data)),
        }

    def normalize(self):
        if self.data is None:
            print("[WARN] No data loaded.")
            return None

        mn = np.nanmin(self.data)
        mx = np.nanmax(self.data)
        if mx == mn:
            return np.zeros_like(self.data)

        return (self.data - mn) / (mx - mn)

    def show(self, title="Raster band"):
        if self.data is None:
            print("[WARN] No data loaded.")
            return

        plt.imshow(self.data, cmap="gray")
        plt.title(title)
        plt.colorbar(label="Value")
        plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# NDVI (Sentinel-2 / Landsat)
# ─────────────────────────────────────────────────────────────────────────────

class NDVIProcessor:
    """
    Computes NDVI = (NIR - RED) / (NIR + RED)
    For Sentinel-2: RED = B4, NIR = B8
    For Landsat 8: RED = B4, NIR = B5
    """

    def __init__(self, red_path: str, nir_path: str):
        self.red_band = RasterBand(red_path)
        self.nir_band = RasterBand(nir_path)
        self.ndvi = None

    def load(self):
        self.red_band.load()
        self.nir_band.load()

    def compute_ndvi(self):
        if self.red_band.data is None or self.nir_band.data is None:
            print("[INFO] Loading bands for NDVI...")
            self.load()

        red = self.red_band.data
        nir = self.nir_band.data

        # Small epsilon to avoid division by zero
        denom = (nir + red + 1e-6)
        self.ndvi = (nir - red) / denom
        return self.ndvi

    def show(self):
        if self.ndvi is None:
            self.compute_ndvi()

        plt.imshow(self.ndvi, cmap="RdYlGn")
        plt.title("NDVI")
        plt.colorbar(label="NDVI")
        plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# Flood detection from Sentinel-1
# ─────────────────────────────────────────────────────────────────────────────

class Sentinel1FloodDetector:
    """
    Very simple flood detection:
    - load VV/VH backscatter band (in dB or sigma0)
    - assume low values = water
    - threshold either given or estimated from a lower percentile
    """

    def __init__(self, path: str):
        self.band = RasterBand(path)
        self.band.load()
        self.flood_mask = None  # boolean 2D array

    def detect(self, threshold: float | None = None, percentile: float = 20.0):
        data = self.band.data
        if data is None:
            print("[ERROR] Sentinel-1 band not loaded.")
            return None

        if threshold is None:
            threshold = np.percentile(data, percentile)
            print(f"[INFO] Auto threshold from {percentile}th percentile: {threshold:.2f}")

        # Flooded pixels = backscatter lower than threshold
        self.flood_mask = data < threshold
        return self.flood_mask

    def show(self):
        if self.flood_mask is None:
            self.detect()

        plt.imshow(self.flood_mask, cmap="Blues")
        plt.title("Estimated flooded areas (1 = water)")
        plt.colorbar()
        plt.show()


# ─────────────────────────────────────────────────────────────────────────────
# Fire detection using FIRMS CSV
# ─────────────────────────────────────────────────────────────────────────────

class FireDetector:
    """
    Processes NASA FIRMS fire points from a CSV file.
    Expect columns like: latitude, longitude, bright_ti4/ti5, confidence, etc.
    """

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.df = None

    def load(self):
        self.df = pd.read_csv(self.csv_path)
        print(f"[INFO] Loaded FIRMS CSV with {len(self.df)} records.")

    def filter_by_confidence(self, min_conf: int = 80):
        if self.df is None:
            self.load()

        if "confidence" not in self.df.columns:
            print("[WARN] 'confidence' column not found, returning all records.")
            return self.df

        filtered = self.df[self.df["confidence"] >= min_conf]
        print(f"[INFO] {len(filtered)} fires with confidence >= {min_conf}.")
        return filtered

    def filter_by_bbox(self, min_lat, max_lat, min_lon, max_lon):
        if self.df is None:
            self.load()

        sel = self.df[
            (self.df["latitude"] >= min_lat)
            & (self.df["latitude"] <= max_lat)
            & (self.df["longitude"] >= min_lon)
            & (self.df["longitude"] <= max_lon)
        ]
        print(f"[INFO] {len(sel)} fires in bounding box.")
        return sel


# ─────────────────────────────────────────────────────────────────────────────
# Copernicus / Sentinel downloader (automatic download)
# ─────────────────────────────────────────────────────────────────────────────

class CopernicusDownloader:
    """
    Small wrapper around 'sentinelsat' for automatic Sentinel downloads.
    You need:
      pip install sentinelsat
      and a Copernicus SciHub or CODE-DE account.

    This is a minimal example – enough for a contest prototype.
    """

    def __init__(self, user: str, password: str,
                 api_url: str = "https://scihub.copernicus.eu/dhus"):
        if SentinelAPI is None:
            raise RuntimeError(
                "sentinelsat is not installed. Run 'pip install sentinelsat'."
            )
        self.api = SentinelAPI(user, password, api_url)

    def search_and_download(self, footprint_geojson: dict,
                            platform_name="Sentinel-2",
                            product_type="S2MSI2A",
                            date=("NOW-7DAYS", "NOW"),
                            limit: int = 1):
        """Search and download newest products for a given AOI."""
        footprint = geojson_to_wkt(footprint_geojson)
        products = self.api.query(
            footprint,
            date=date,
            platformname=platform_name,
            producttype=product_type,
        )
        if not products:
            print("[INFO] No products found.")
            return

        df = self.api.to_dataframe(products)
        df = df.sort_values("ingestiondate", ascending=False)

        if limit is not None:
            df = df.head(limit)

        print(f"[INFO] Downloading {len(df)} products...")
        self.api.download_all(df.index)


# ─────────────────────────────────────────────────────────────────────────────
# Simple end-to-end SAFE-RO pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run_safe_ro_pipeline(
    s1_flood_path: str,
    red_path: str,
    nir_path: str,
    firms_csv: str,
    flood_threshold: float | None = None,
):
    """
    Example pipeline combining:
    - NDVI (vegetation state)
    - Flood detection from Sentinel-1
    - Fire detection from FIRMS

    Returns a dictionary with core products.
    """

    # NDVI
    ndvi_proc = NDVIProcessor(red_path, nir_path)
    ndvi = ndvi_proc.compute_ndvi()
    ndvi_stats = {
        "min": float(np.nanmin(ndvi)),
        "max": float(np.nanmax(ndvi)),
        "mean": float(np.nanmean(ndvi)),
    }

    # Floods
    flood_det = Sentinel1FloodDetector(s1_flood_path)
    flood_mask = flood_det.detect(threshold=flood_threshold)
    flood_percent = float(np.mean(flood_mask) * 100.0)

    # Fires
    fire_det = FireDetector(firms_csv)
    fires_high_conf = fire_det.filter_by_confidence(80)

    result = {
        "ndvi": ndvi,
        "ndvi_stats": ndvi_stats,
        "flood_mask": flood_mask,
        "flooded_area_percent": flood_percent,
        "fires_high_conf": fires_high_conf,
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Quick local test (optional)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("This is the SAFE-RO core module. Import it or run specific tests here.")
