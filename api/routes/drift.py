from fastapi import APIRouter
import pandas as pd

from api.services.drift_service import detect_drift
from features.build_features import build_features

TARGET = "Resigned"

router = APIRouter()

windows = [
    "data/processed/window1.csv",
    "data/processed/window2.csv",
]

@router.get("/drift")
def get_drift():

    reference = build_features(pd.read_csv(windows[0]))
    current = build_features(pd.read_csv(windows[1]))

    result = detect_drift(
        reference.drop(columns=[TARGET, "Hire_Date"]),
        current.drop(columns=[TARGET, "Hire_Date"])
    )

    return result