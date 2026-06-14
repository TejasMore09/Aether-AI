import pandas as pd
import joblib
import mlflow
import mlflow.sklearn
from xgboost import XGBClassifier
from sklearn.metrics import f1_score, roc_auc_score
from features.build_features import build_features

# ---------------------------------------------
# Configuration
# ---------------------------------------------
TARGET = "Resigned"
BASELINE_MODEL_PATH = "models/domains/hr_attrition_model.pkl"
ENCODER_PATH = "models/domains/hr_attrition_encoders.pkl"
ADAPTED_MODEL_PATH = "models/domains/hr_attrition_model.pkl"
ADAPTED_ENCODER_PATH = "models/domains/hr_attrition_encoders.pkl"
mlflow.set_experiment("SelfEvolvingAI-Adaptation")

# ---------------------------------------------
# Load Artifacts
# ---------------------------------------------
def load_artifacts():
    baseline_model = joblib.load(BASELINE_MODEL_PATH)
    encoders = joblib.load(ENCODER_PATH)
    return baseline_model, encoders

# ---------------------------------------------
# Encoding Function (Reusable)
# ---------------------------------------------
def encode(df, encoders):
    X = df.drop(columns=[TARGET, "Hire_Date"])
    for col, le in encoders.items():
        if col in X.columns:
            X[col] = le.transform(X[col])
    return X

# ---------------------------------------------
# Evaluate Model
# ---------------------------------------------
def evaluate_model(model, X, y):
    preds = model.predict(X)
    probs = model.predict_proba(X)[:, 1]
    f1 = f1_score(y, preds)
    roc_auc = roc_auc_score(y, probs)
    return f1, roc_auc

# ---------------------------------------------
# Adaptation Logic
# ---------------------------------------------
def run_adaptation(reference_path, current_path):
    """
    reference_path → previous stable window
    current_path   → new incoming data
    """
    baseline_model, encoders = load_artifacts()
    # Load & feature engineer
    ref_df = build_features(pd.read_csv(reference_path))
    cur_df = build_features(pd.read_csv(current_path))

    X_ref = encode(ref_df, encoders)
    y_ref = ref_df[TARGET]
    X_cur = encode(cur_df, encoders)
    y_cur = cur_df[TARGET]

    # Evaluate baseline
    baseline_f1, baseline_auc = evaluate_model(baseline_model, X_cur, y_cur)
    print("Baseline F1:", baseline_f1)
    print("Baseline ROC-AUC:", baseline_auc)
    with mlflow.start_run(run_name="adaptive_xgb_run"):
        model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            scale_pos_weight=8,
            eval_metric="logloss"
        )
        model.fit(X_ref, y_ref)
        new_f1, new_auc = evaluate_model(model, X_cur, y_cur)
        print("Adapted F1:", new_f1)
        print("Adapted ROC-AUC:", new_auc)

        # Log to MLflow
        mlflow.log_param("model_type", "XGBoost")
        mlflow.log_metric("baseline_f1", baseline_f1)
        mlflow.log_metric("baseline_roc_auc", baseline_auc)
        mlflow.log_metric("adapted_f1", new_f1)
        mlflow.log_metric("adapted_roc_auc", new_auc)
        mlflow.sklearn.log_model(model, name="adapted_model")
        adapted = False
        if new_f1 > baseline_f1:
            joblib.dump(model, ADAPTED_MODEL_PATH)
            joblib.dump(encoders, ADAPTED_ENCODER_PATH)
            print("Model adapted and saved.")
            adapted = True
        else:
            print("No adaptation applied (baseline better).")

    return {
        "baseline_f1": float(baseline_f1),
        "baseline_roc_auc": float(baseline_auc),
        "adapted_f1": float(new_f1),
        "adapted_roc_auc": float(new_auc),
        "adapted": adapted
    }

# ---------------------------------------------
# Safe Script Execution
# ---------------------------------------------
if __name__ == "__main__":

    results = run_adaptation(
        "data/processed/window1.csv",
        "data/processed/window2.csv"
    )
    print("\nAdaptation Summary:")
    print(results)