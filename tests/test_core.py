import os
import sys
import numpy as np
import rasterio
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Corrected import path after refactoring
from safe_ro.core.safe_ro_core import RasterBand, NDVIProcessor, Sentinel1FloodDetector

# --- Test Setup ---


@pytest.fixture(scope="module")
def create_dummy_raster():
    """Creates a dummy raster file for testing and yields its path."""
    dummy_files = []

    def _create_file(name, dtype="uint16", count=1, width=10, height=10):
        path = f"{name}.tif"
        profile = {
            "driver": "GTiff",
            "dtype": dtype,
            "count": count,
            "width": width,
            "height": height,
            "crs": "EPSG:4326",
            "transform": rasterio.transform.from_origin(-74.0, 40.7, 1, 1),
        }
        # Ensure the file is created with some data
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(np.random.randint(1, 255, (height, width)).astype(dtype), 1)

        dummy_files.append(path)
        return path

    yield _create_file

    # Teardown: remove all created dummy files
    for f in dummy_files:
        if os.path.exists(f):
            os.remove(f)


# --- Tests ---


def test_raster_band_loading(create_dummy_raster):
    """Tests if the RasterBand class can successfully load a file."""
    dummy_path = create_dummy_raster("test_band_loading")
    band = RasterBand(dummy_path)
    # Pass downsample_factor=1 to avoid shape changes
    data = band.load(downsample_factor=1)
    assert data is not None
    assert data.shape == (10, 10)
    print("✅ RasterBand loading test passed.")


def test_ndvi_computation(create_dummy_raster):
    """Tests if the NDVIProcessor can compute NDVI without errors."""
    red_path = create_dummy_raster("test_red_ndvi", width=10, height=10)
    nir_path = create_dummy_raster("test_nir_ndvi", width=10, height=10)

    processor = NDVIProcessor(red_path, nir_path)
    ndvi, bounds = processor.compute_ndvi()

    assert ndvi is not None
    assert bounds is not None
    assert ndvi.shape == (10, 10)
    assert np.all(ndvi >= -1) and np.all(ndvi <= 1)
    print("✅ NDVI computation test passed.")


def test_flood_detection(create_dummy_raster):
    """Tests if the Sentinel1FloodDetector can process a file with a specific threshold."""
    s1_path = create_dummy_raster("test_s1_vv_flood", dtype="float32")

    detector = Sentinel1FloodDetector(s1_path)
    # Pass an explicit threshold to the detect method
    flood_mask, bounds = detector.detect(threshold=0.5)

    assert flood_mask is not None
    assert bounds is not None
    assert flood_mask.shape == (10, 10)
    assert np.all(np.isin(flood_mask, [0, 1]))
    print("✅ Flood detection test passed.")
