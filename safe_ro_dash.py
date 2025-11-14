import tempfile
from pathlib import Path

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import rasterio

from safe_ro_core import NDVIProcessor, Sentinel1FloodDetector, FireDetector


st.set_page_config(page_title="SAFE-RO Dashboard", layout="wide")

st.title("🛰️ SAFE-RO – Satellite Hazard Dashboard")

st.markdown(
    """
This is a prototype dashboard for the SAFE-RO project.
Upload satellite bands and FIRMS CSV to compute:
- NDVI (vegetation)
- Flooded area (Sentinel-1)
- High-confidence fires (FIRMS)
"""
)

# Helper: save uploaded file to a temporary path so rasterio/pandas can read it
def save_upload(uploaded_file, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.read())
    tmp.flush()
    return tmp.name


# ---------------- NDVI section ---------------- #

st.header("1. NDVI from Sentinel / Landsat")

col1, col2 = st.columns(2)

with col1:
    red_file = st.file_uploader("RED band (.tif)", type=["tif", "tiff"], key="red")
with col2:
    nir_file = st.file_uploader("NIR band (.tif)", type=["tif", "tiff"], key="nir")

if red_file and nir_file:
    red_path = save_upload(red_file, ".tif")
    nir_path = save_upload(nir_file, ".tif")

    proc = NDVIProcessor(red_path, nir_path)
    ndvi = proc.compute_ndvi()

    stats = {
        "min": float(np.nanmin(ndvi)),
        "max": float(np.nanmax(ndvi)),
        "mean": float(np.nanmean(ndvi)),
    }
    st.write("**NDVI statistics:**", stats)

    fig, ax = plt.subplots()
    im = ax.imshow(ndvi, cmap="RdYlGn")
    ax.set_title("NDVI")
    fig.colorbar(im, ax=ax, label="NDVI")
    st.pyplot(fig)
else:
    st.info("Upload both RED and NIR bands to compute NDVI.")


# ---------------- Flood detection section ---------------- #

st.header("2. Flood detection from Sentinel-1")

s1_file = st.file_uploader("Sentinel-1 VV/VH band (.tif)", type=["tif", "tiff"], key="s1")
threshold = st.text_input("Optional threshold (leave empty for automatic)", value="")

if s1_file:
    s1_path = save_upload(s1_file, ".tif")

    thr_val = None
    if threshold.strip():
        try:
            thr_val = float(threshold)
        except ValueError:
            st.warning("Invalid threshold. Using automatic percentile instead.")

    det = Sentinel1FloodDetector(s1_path)
    mask = det.detect(threshold=thr_val)
    flooded_percent = float(mask.mean() * 100.0)

    st.write(f"**Estimated flooded area:** {flooded_percent:.2f}% of pixels")

    fig2, ax2 = plt.subplots()
    im2 = ax2.imshow(mask, cmap="Blues")
    ax2.set_title("Flood mask (True = flooded)")
    fig2.colorbar(im2, ax=ax2)
    st.pyplot(fig2)
else:
    st.info("Upload a Sentinel-1 band to estimate flooded area.")


# ---------------- Fire detection section ---------------- #

st.header("3. Fire detections from FIRMS")

csv_file = st.file_uploader("FIRMS CSV file", type=["csv"], key="firms")
min_conf = st.slider("Minimum confidence", min_value=0, max_value=100, value=80, step=5)

if csv_file:
    csv_path = save_upload(csv_file, ".csv")

    det = FireDetector(csv_path)
    fires = det.filter_by_confidence(min_conf)
    st.write(f"**Number of fires with confidence ≥ {min_conf}:** {len(fires)}")

    st.dataframe(fires.head(20))
else:
    st.info("Upload a FIRMS CSV file to see fire detections.")
