import pandas as pd
import joblib
from features.build_features import build_features
from evaluation.window_experiment import train, evaluate
from api.services.drift_service import detect_drift

TARGET = "Resigned"
PERFORMANCE_THRESHOLD = 0.5
DRIFT_THRESHOLD = 30.0

def adaptive_check():
    w1 = build_features(pd.read_csv("data/processed/window1.csv"))
    w2 = build_features(pd.read_csv("data/processed/window2.csv"))
    model, encoders = train(w1)
    performance = evaluate(model, encoders, w2)
    drift = detect_drift(
        w1.drop(columns=[TARGET, "Hire_Date"]),
        w2.drop(columns=[TARGET, "Hire_Date"])
    )
    adapt_triggered = False
    if performance["roc_auc"] < PERFORMANCE_THRESHOLD or \
       drift["drift_percentage"] > DRIFT_THRESHOLD:
        # Retrain using both windows
        combined = pd.concat([w1, w2])
        model, encoders = train(combined)
        joblib.dump(model, "models/adapted_xgb.pkl")
        joblib.dump(encoders, "models/adapted_encoders.pkl")
        adapt_triggered = True
    return {
        "roc_auc": performance["roc_auc"],
        "f1": performance["f1"],
        "drift_percentage": drift["drift_percentage"],
        "adapted": adapt_triggered
    }