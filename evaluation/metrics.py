import pandas as pd
import joblib
from sklearn.metrics import f1_score, roc_auc_score

TARGET = "Resigned"

# Load models
baseline_model = joblib.load("models/baseline_xgb.pkl")
adapted_model = joblib.load("models/adapted_xgb.pkl")
encoders = joblib.load("models/adapted_encoders.pkl")

# Encoding
def encode(df):
    X = df.drop(columns=[TARGET, "Hire_Date"])
    for col, le in encoders.items():
        X[col] = le.transform(X[col])
    return X

# Load test window
test_df = pd.read_csv("data/processed/window3.csv")
X_test = encode(test_df)
y_test = test_df[TARGET]

# Baseline evaluation
b_preds = baseline_model.predict(X_test)
b_probs = baseline_model.predict_proba(X_test)[:,1]
baseline_f1 = f1_score(y_test, b_preds)
baseline_roc = roc_auc_score(y_test, b_probs)

# Adapted evaluation
a_preds = adapted_model.predict(X_test)
a_probs = adapted_model.predict_proba(X_test)[:,1]
adapted_f1 = f1_score(y_test, a_preds)
adapted_roc = roc_auc_score(y_test, a_probs)

# Results
print("\nEVALUATION RESULTS\n")
print(f"Baseline Model  -> F1: {baseline_f1:.4f}, ROC-AUC: {baseline_roc:.4f}")
print(f"Adaptive Model  -> F1: {adapted_f1:.4f}, ROC-AUC: {adapted_roc:.4f}")
