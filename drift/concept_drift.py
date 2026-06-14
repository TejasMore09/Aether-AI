import pandas as pd
import joblib
from sklearn.metrics import f1_score, roc_auc_score
from features.build_features import build_features

model = joblib.load("models/baseline_xgb.pkl")
encoders = joblib.load("models/encoders.pkl")

def encode(df):
    X = df.drop(columns=["Resigned", "Hire_Date"])
    for col, le in encoders.items():
        X[col] = le.transform(X[col])
    return X

for w in ["window2","window3","window4"]:
    df = build_features(pd.read_csv(f"data/processed/{w}.csv"))
    X = encode(df)
    y = df["Resigned"]

    preds = model.predict(X)
    probs = model.predict_proba(X)[:,1]

    print(f"{w.upper()} -> F1: {f1_score(y,preds):.4f}, ROC-AUC: {roc_auc_score(y,probs):.4f}")
