import pandas as pd
import joblib
import numpy as np

from sklearn.metrics import roc_auc_score, f1_score, precision_recall_curve
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from features.build_features import build_features

TARGET = "Resigned"


def encode(df, encoders):
    X = df.drop(columns=[TARGET, "Hire_Date"])
    for col, le in encoders.items():
        X[col] = le.transform(X[col])
    return X

def train(df):
    X = df.drop(columns=[TARGET, "Hire_Date"])
    y = df[TARGET]
    encoders = {}
    for col in X.select_dtypes(include="object").columns:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col])
        encoders[col] = le
    model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        eval_metric="logloss",
        random_state=42
    )
    model.fit(X, y)
    return model, encoders

def evaluate(model, encoders, df):
    X = encode(df, encoders)
    y = df[TARGET]
    probs = model.predict_proba(X)[:,1]
    roc = roc_auc_score(y, probs)
    # threshold optimization
    precision, recall, thresholds = precision_recall_curve(y, probs)
    f1_scores = 2 * (precision * recall) / (precision + recall + 1e-8)
    best_threshold = thresholds[np.argmax(f1_scores)]
    preds = (probs >= best_threshold).astype(int)
    f1 = f1_score(y, preds)
    return {
        "roc_auc": float(roc),
        "f1": float(f1),
        "threshold": float(best_threshold)
    }


if __name__ == "__main__":
    windows = []
    for i in range(1,5):
        df = build_features(pd.read_csv(f"data/processed/window{i}.csv"))
        windows.append(df)
    print("\nTrain on Window1")
    model, encoders = train(windows[0])
    for i in range(1,4):
        print(f"\nTest on Window{i+1}")
        print(evaluate(model, encoders, windows[i]))

    print("\nAdaptive Retraining")
    model2, encoders2 = train(pd.concat(windows[:2]))
    print("\nRetrained → Test Window3")
    print(evaluate(model2, encoders2, windows[2]))
    model3, encoders3 = train(pd.concat(windows[:3]))
    print("\nRetrained → Test Window4")
    print(evaluate(model3, encoders3, windows[3]))