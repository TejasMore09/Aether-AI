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

    drifted_features = [
        col for col, info in drift_by_columns.items()
        if info["drift_detected"]
    ]

    return drifted_features


if __name__ == "__main__":

    w1 = build_features(pd.read_csv("data/processed/window1.csv"))
    w2 = build_features(pd.read_csv("data/processed/window2.csv"))
    w3 = build_features(pd.read_csv("data/processed/window3.csv"))
    w4 = build_features(pd.read_csv("data/processed/window4.csv"))

    ref = w1.drop(columns=[TARGET, "Hire_Date"])

    for name, df in {
        "W2": w2,
        "W3": w3,
        "W4": w4
    }.items():

        cur = df.drop(columns=[TARGET, "Hire_Date"])
        drifted = detect_drift(ref, cur)

        print(f"\n{name} Drifted Features ({len(drifted)}):")
        print(drifted[:10])
