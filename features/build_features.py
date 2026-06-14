import pandas as pd

def build_features(df):
    df = df.copy()

    df["workload_index"] = (
        df["Work_Hours_Per_Week"] +
        df["Overtime_Hours"] +
        df["Projects_Handled"]
    )

    df["stability_index"] = (
        df["Years_At_Company"] -
        df["Promotions"]
    )

    df["health_risk_score"] = (
        df["Sick_Days"] +
        (100 - df["Employee_Satisfaction_Score"])
    )

    df["training_intensity"] = (
        df["Training_Hours"] /
        (df["Years_At_Company"] + 1)
    )

    return df