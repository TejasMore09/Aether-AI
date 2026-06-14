import pandas as pd
from evidently.legacy.report import Report
from evidently.legacy.metrics import DataDriftTable
from features.build_features import build_features

TARGET = "Resigned"
def detect_drift(reference_df, current_df):
    report = Report(metrics=[DataDriftTable()])
    report.run(reference_data=reference_df, current_data=current_df)
    result = report.as_dict()
    drift_by_columns = result["metrics"][0]["result"]["drift_by_columns"]
    drifted = [
        col for col, info in drift_by_columns.items()
        if info["drift_detected"]
    ]
    total_features = len(drift_by_columns)
    drift_percent = (len(drifted) / total_features) * 100
    return {
        "drifted_features": drifted,
        "drift_percentage": drift_percent
    }