"""
FastAPI wrapper around SAFE-RO core.
Run with:
    uvicorn safe_ro.interfaces.safe_ro_api:app --reload
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

# Corrected import path after refactoring
from safe_ro.core.safe_ro_core import NDVIProcessor, Sentinel1FloodDetector

app = FastAPI(title="SAFE-RO API", version="0.1.0")


class NDVIRequest(BaseModel):
    red_path: str
    nir_path: str


class FloodRequest(BaseModel):
    s1_path: str
    threshold: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ndvi")
def ndvi_endpoint(req: NDVIRequest):
    proc = NDVIProcessor(req.red_path, req.nir_path)
    ndvi, _ = proc.compute_ndvi()  # Unpack tuple
    if ndvi is not None:
        stats = {
            "min": float(ndvi.min()),
            "max": float(ndvi.max()),
            "mean": float(ndvi.mean()),
        }
        return {"stats": stats}
    return {"error": "Could not compute NDVI"}


@app.post("/flood")
def flood_endpoint(req: FloodRequest):
    det = Sentinel1FloodDetector(req.s1_path)
    mask, _ = det.detect(threshold=req.threshold)  # Unpack tuple
    if mask is not None:
        flooded_percent = float(mask.mean() * 100.0)
        return {"flooded_area_percent": flooded_percent}
    return {"error": "Could not compute flood mask"}


@app.get("/")
def read_root():
    return {"message": "Welcome to the SAFE-RO API"}
