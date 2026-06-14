import pandas as pd
import numpy as np
import os
import joblib
import json
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
from sklearn.preprocessing import LabelEncoder
from statsmodels.tsa.statespace.sarimax import SARIMAX
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from database.db import engine, SessionLocal
from database.models import ExperimentRun

DOMAINS = {
    "hr_attrition": "attrition",
    "fin_fraud": "is_fraud",
    "crm_churn": "churn",
    "sec_threats": "attack_detected",
    "market_leads": "conversion",
    "supply_chain": "demand_volume"
}

def train_all_models():
    models_dir = os.path.join(BASE_DIR, "models", "domains")
    os.makedirs(models_dir, exist_ok=True)
    
    for domain, target_col in DOMAINS.items():
        print(f"Training Optimal Model for {domain}...")
        
        # We train on the baseline Window 1 (2022 data)
        query = f"SELECT * FROM {domain} WHERE timestamp >= '2022-01-01' AND timestamp < '2023-01-01'"
        df = pd.read_sql(query, con=engine)
        
        if len(df) == 0:
            print(f"Skipping {domain} - No training data found.")
            continue
            
        # Time Series Modeling
        if domain == "supply_chain":
            df = df.sort_values('timestamp').set_index('timestamp')
            y = df[target_col]
            
            # Train SARIMAX (Seasonal ARIMA) to capture the exact seasonality injected
            model = SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7)) # Weekly seasonality approximation
            model_fit = model.fit(disp=False)
            
            model_path = os.path.join(models_dir, f"{domain}_model.pkl")
            joblib.dump(model_fit, model_path)
            print(f"Saved {domain} SARIMAX model -> {model_path}")
            continue

        # Classification Modeling for others
        drop_cols = [target_col, "id", "timestamp"]
        X = df.drop(columns=[col for col in drop_cols if col in df.columns])
        y = df[target_col]
        
        # Evaluate Categorical Encoders First
        encoders = {}
        for col in X.select_dtypes(include=['object']).columns:
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            encoders[col] = le
            
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
            
        # Candidate 1: XGBoost
        model_xgb = XGBClassifier(n_estimators=100, learning_rate=0.1, max_depth=6, random_state=42, eval_metric="logloss")
        model_xgb.fit(X_train, y_train)
        preds_xgb = model_xgb.predict(X_test)
        f1_xgb = f1_score(y_test, preds_xgb)
        
        # Candidate 2: Random Forest
        model_rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        model_rf.fit(X_train, y_train)
        preds_rf = model_rf.predict(X_test)
        f1_rf = f1_score(y_test, preds_rf)
        
        # Select Best Model (Multi-Model Management 6.2)
        if f1_xgb >= f1_rf:
            best_model = model_xgb
            best_f1 = f1_xgb
            algo_name = "XGBoost"
            hyperparams = {"n_estimators": 100, "learning_rate": 0.1, "max_depth": 6}
        else:
            best_model = model_rf
            best_f1 = f1_rf
            algo_name = "Random Forest"
            hyperparams = {"n_estimators": 100, "max_depth": 10}
            
        # Re-train best model on full data
        best_model.fit(X, y)
        
        # Log to Experiment Tracker (6.1)
        db = SessionLocal()
        exp = ExperimentRun(
            domain=domain,
            model_type=algo_name,
            hyperparams=json.dumps(hyperparams),
            metrics=json.dumps({"f1_score": round(best_f1, 4), "competitor_f1": round(min(f1_xgb, f1_rf), 4)}),
            dataset_window="2022-01-01 to 2023-01-01",
            notes=f"Auto-selected {algo_name} over competitor."
        )
        db.add(exp)
        db.commit()
        db.close()
        
        # Save best model and encoders
        model_path = os.path.join(models_dir, f"{domain}_model.pkl")
        encoder_path = os.path.join(models_dir, f"{domain}_encoders.pkl")
        
        joblib.dump(best_model, model_path)
        joblib.dump(encoders, encoder_path)
        print(f"Saved {domain} {algo_name} model (F1: {best_f1:.4f}) -> {model_path}")

if __name__ == "__main__":
    train_all_models()
    print("All enterprise models trained and saved successfully!")
