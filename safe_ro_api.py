"""
FastAPI wrapper around SAFE-RO core.
Run with:
    uvicorn safe_ro_api:app --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from safe_ro_core import NDVIProcessor, Sentinel1FloodDetector, FireDetector

app = FastAPI(title="SAFE-RO API", version="0.1.0")


class NDVIRequest(BaseModel):
    red_path: str
    nir_path: str


class FloodRequest(BaseModel):
    s1_path: str
    threshold: Optional[float] = None


class FireRequest(BaseModel):
    csv_path: str
    min_confidence: int = 80


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ndvi")
def ndvi_endpoint(req: NDVIRequest):
    proc = NDVIProcessor(req.red_path, req.nir_path)
    ndvi = proc.compute_ndvi()
    stats = {
        "min": float(ndvi.min()),
        "max": float(ndvi.max()),
        "mean": float(ndvi.mean()),
    }
    return {"stats": stats}


@app.post("/flood")
def flood_endpoint(req: FloodRequest):
    det = Sentinel1FloodDetector(req.s1_path)
    mask = det.detect(threshold=req.threshold)
    flooded_percent = float(mask.mean() * 100.0)
    return {"flooded_area_percent": flooded_percent}


@app.post("/fires")
def fires_endpoint(req: FireRequest):
    det = FireDetector(req.csv_path)
    fires = det.filter_by_confidence(req.min_confidence)
    return {
        "count": int(len(fires)),
        "example": fires.head(5).to_dict(orient="records"),
    }
