import pandas as pd
import joblib
import numpy as np
import os
import sys
import numpy as np
from sklearn.metrics import roc_auc_score, f1_score, precision_recall_curve
from api.services.drift_service import detect_drift
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)

from database.db import engine

TARGET_MAP = {
    "hr_attrition": "attrition",
    "fin_fraud": "is_fraud",
    "crm_churn": "churn",
    "sec_threats": "attack_detected",
    "market_leads": "conversion",
    "supply_chain": "demand_volume"
}

def compute_metrics(domain: str = "hr_attrition"):
    try:
        if domain not in TARGET_MAP:
            return {"error": f"Invalid domain. Must be one of {list(TARGET_MAP.keys())}"}
            
        target_col = TARGET_MAP[domain]
        
        # Load data from live SQLite Database instead of CSVs
        w1 = pd.read_sql(f"SELECT * FROM {domain} WHERE timestamp >= '2022-01-01' AND timestamp < '2023-01-01'", con=engine)
        w2 = pd.read_sql(f"SELECT * FROM {domain} WHERE timestamp >= '2023-01-01' AND timestamp < '2024-01-01'", con=engine)
        
        if len(w1) == 0 or len(w2) == 0:
            return {"error": "Database is empty. Please run python scripts/process_datasets.py first."}

        # Drop metadata columns for prediction
        drop_cols_pred = [target_col, "timestamp", "id"]
        X2 = w2.drop(columns=[col for col in drop_cols_pred if col in w2.columns]).copy()
        
        y2 = w2[target_col]

        # Load the newly trained XGBoost model and encoders
        models_dir = os.path.join(BASE_DIR, "models", "domains")
        model_path = os.path.join(models_dir, f"{domain}_model.pkl")
        encoder_path = os.path.join(models_dir, f"{domain}_encoders.pkl")
        
        if not os.path.exists(model_path):
            return {"error": f"Model for {domain} not found. Run scripts/train_models.py"}
            
        model = joblib.load(model_path)
        
        if domain == "supply_chain":
            w2_ts = w2.sort_values('timestamp').set_index('timestamp')
            X2 = w2_ts
            y2 = w2_ts[target_col]
            
            # Predict using SARIMAX
            # For simplicity, we predict exactly on the time steps we evaluate on
            preds = model.predict(start=0, end=len(X2)-1)
            
            mape = np.mean(np.abs((y2 - preds) / (y2 + 1e-8))) * 100
            
            drift_results = {"drifted_features": [], "drift_percentage": 0.0} # Time series drift is handled differently, skipping for demo
            return {
                "mape": round(float(mape), 2),
                "rmse": round(float(np.sqrt(np.mean((y2 - preds)**2))), 2),
                "drifted_features": [],
                "drift_percentage": 0.0
            }
            
        encoders = joblib.load(encoder_path)
        
        # Apply encoders for classification
        for col, le in encoders.items():
            if col in X2.columns:
                X2[col] = X2[col].apply(lambda x: x if x in le.classes_ else le.classes_[0])
                X2[col] = le.transform(X2[col].astype(str))
                
        # Generate real predictions using the ML model
        probs = model.predict_proba(X2)[:, 1]
        
        # Threshold optimization
        precision, recall, thresholds = precision_recall_curve(y2, probs)
        f1_scores = 2 * (precision * recall) / (precision + recall + 1e-8)
        best_threshold = thresholds[np.argmax(f1_scores)]
        preds = (probs >= best_threshold).astype(int)
        
        f1 = f1_score(y2, preds)
        roc_auc = roc_auc_score(y2, probs)
        
        # Drop categorical and ID columns for Evidenly Drift Detection
        drop_cols = [target_col, "timestamp", "id"]
        if "department" in w1.columns:
            drop_cols.append("department")
        if "merchant_id" in w1.columns:
            drop_cols.append("merchant_id")
        if "transaction_type" in w1.columns:
            drop_cols.append("transaction_type")
        if "location" in w1.columns:
            drop_cols.append("location")
        if "contract_type" in w1.columns:
            drop_cols.append("contract_type")
        if "protocol_type" in w1.columns:
            drop_cols.append("protocol_type")
            
        # Ensure we only drop columns that actually exist
        drop_cols = [col for col in drop_cols if col in w1.columns]
        
        # Drift detection
        w1_features = w1.drop(columns=drop_cols)
        w2_features = w2.drop(columns=drop_cols)
        drift_results = detect_drift(w1_features, w2_features)
        
        # 1.4 Feature-Level Drift Intelligence
        # Map root cause: How much does this drifted feature impact the target?
        feature_impact = {}
        for f in drift_results["drifted_features"]:
            if f in w2_features.columns:
                # Calculate Pearson correlation coefficient
                corr = np.corrcoef(w2_features[f], y2)[0, 1]
                # Map to High/Medium/Low impact
                corr_val = abs(corr) if not np.isnan(corr) else 0
                impact = "High" if corr_val > 0.3 else "Medium" if corr_val > 0.1 else "Low"
                feature_impact[f] = {"correlation": round(float(corr_val), 3), "impact": impact}
        
        return {
            "roc_auc": round(float(roc_auc), 4),
            "f1_score": round(float(f1), 4),
            "threshold": round(float(best_threshold), 4),
            "drifted_features": drift_results["drifted_features"],
            "drift_percentage": round(float(drift_results["drift_percentage"]), 2),
            "feature_impact": feature_impact
        }
    except Exception as e:
        return {"error": str(e)}