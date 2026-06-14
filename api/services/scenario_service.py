"""
Section 2.4: Scenario Simulator
Applies in-memory distribution shifts to live database data and re-evaluates
the Decision Engine — without writing corrupted data back to disk.
"""
import numpy as np
import pandas as pd
from sqlalchemy import text
from database.db import engine
from api.services.decision_engine import DecisionEngine
from api.services.model_service import compute_metrics


NUMERIC_DROP = ["id", "attrition", "is_fraud", "churn", "attack_detected", "conversion", "demand_volume", "timestamp"]

def run_scenario(domain: str, feature: str, shift_pct: float) -> dict:
    """
    Shift a single feature distribution by shift_pct% (e.g., +20 or -30),
    then recalculate drift and run the Decision Engine.
    Returns the before/after comparison and financial impact delta.
    """
    # --- Load reference window (2022) and current window (2023) ---
    ref_df = pd.read_sql(
        text(f"SELECT * FROM {domain} WHERE timestamp < '2023-01-01'"),
        con=engine
    )
    cur_df = pd.read_sql(
        text(f"SELECT * FROM {domain} WHERE timestamp >= '2023-01-01' AND timestamp < '2024-01-01'"),
        con=engine
    )

    if ref_df.empty or cur_df.empty:
        return {"error": "Insufficient data for scenario simulation."}

    # --- Baseline: real metrics and decision ---
    baseline_metrics = compute_metrics(domain)
    
    # Calculate baseline drift manually
    numeric_cols = [c for c in ref_df.select_dtypes(include=[np.number]).columns if c not in NUMERIC_DROP]
    baseline_drift_pct = 0.0
    drifted = []
    for col in numeric_cols:
        ref_mean, ref_std = ref_df[col].mean(), ref_df[col].std()
        cur_mean = cur_df[col].mean()
        if ref_std > 0:
            z = abs(cur_mean - ref_mean) / ref_std
            if z > 0.5:
                drifted.append(col)
    baseline_drift_pct = len(drifted) / max(len(numeric_cols), 1) * 100
    baseline_drift = {"drift_percentage": baseline_drift_pct, "drifted_features": drifted}
    baseline_decision = DecisionEngine.evaluate(domain, baseline_metrics, baseline_drift)

    # --- Scenario: apply shift to the target feature ---
    if feature not in cur_df.columns:
        return {"error": f"Feature '{feature}' not found in domain '{domain}'."}

    scenario_df = cur_df.copy()
    multiplier = 1.0 + (shift_pct / 100.0)
    scenario_df[feature] = scenario_df[feature] * multiplier

    # Recalculate drift with shifted data
    scenario_drifted = []
    for col in numeric_cols:
        ref_mean, ref_std = ref_df[col].mean(), ref_df[col].std()
        cur_mean = (scenario_df[col].mean() if col == feature else cur_df[col].mean())
        if ref_std > 0:
            z = abs(cur_mean - ref_mean) / ref_std
            if z > 0.5:
                scenario_drifted.append(col)
    scenario_drift_pct = len(scenario_drifted) / max(len(numeric_cols), 1) * 100
    scenario_drift = {"drift_percentage": scenario_drift_pct, "drifted_features": scenario_drifted}
    scenario_decision = DecisionEngine.evaluate(domain, baseline_metrics, scenario_drift)

    return {
        "domain": domain,
        "feature_shifted": feature,
        "shift_pct": shift_pct,
        "baseline": {
            "drift_percentage": round(baseline_drift_pct, 2),
            "drifted_features": drifted,
            "action": baseline_decision["action"],
            "risk_level": baseline_decision["risk_level"],
            "expected_daily_loss_usd": baseline_decision["expected_daily_loss_usd"]
        },
        "scenario": {
            "drift_percentage": round(scenario_drift_pct, 2),
            "drifted_features": scenario_drifted,
            "action": scenario_decision["action"],
            "risk_level": scenario_decision["risk_level"],
            "expected_daily_loss_usd": scenario_decision["expected_daily_loss_usd"]
        },
        "delta_loss_usd": round(scenario_decision["expected_daily_loss_usd"] - baseline_decision["expected_daily_loss_usd"], 2),
        "decision_changed": baseline_decision["action"] != scenario_decision["action"],
        "available_features": numeric_cols
    }
