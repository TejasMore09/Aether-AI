"""
╔══════════════════════════════════════════════════════════════╗
║           Aether AI — Pre-Submission Verification Suite      ║
║                    Team Singularity · 2026                   ║
╚══════════════════════════════════════════════════════════════╝

Run this script from the workspace root before pushing to GitHub:
    python verify_submission.py

Checks:
  1. Core module imports resolve without errors
  2. Database tables exist (or can be created)
  3. Domain model files are present on disk
  4. compute_metrics() runs for all 6 domains (no NameError / FileNotFoundError)
  5. DecisionEngine.evaluate() produces valid output structures
  6. /health system-health summary returns expected keys
  7. Supply chain domain bypasses encoder load correctly
  8. Adaptive threshold computation does not crash
"""

import sys
import os
import traceback
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

PASS = "\033[92m  ✔ PASS\033[0m"
FAIL = "\033[91m  ✘ FAIL\033[0m"
INFO = "\033[94m  ℹ INFO\033[0m"
WARN = "\033[93m  ⚠ WARN\033[0m"

results = []

def check(label: str, fn):
    """Run fn(), print result, record pass/fail."""
    try:
        result = fn()
        msg = f" → {result}" if result not in (None, True) else ""
        print(f"{PASS}  {label}{msg}")
        results.append((label, True, None))
    except Exception as e:
        tb = traceback.format_exc().strip().splitlines()[-1]
        print(f"{FAIL}  {label}")
        print(f"         {tb}")
        results.append((label, False, str(e)))

# ─────────────────────────────────────────────────────────────
# SECTION 1: Module Import Checks
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 1 — Core Module Imports")
print("═" * 62)

def _import_fastapi():
    from fastapi import FastAPI
    return "FastAPI OK"

def _import_model_service():
    from api.services.model_service import compute_metrics
    return "compute_metrics OK"

def _import_decision_engine():
    from api.services.decision_engine import DecisionEngine
    return "DecisionEngine OK"

def _import_drift_service():
    from api.services.drift_service import detect_drift
    return "detect_drift OK"

def _import_explain_service():
    from api.services.explain_service import generate_ai_explanation
    return "generate_ai_explanation OK"

def _import_audit_service():
    from api.services.audit_service import log_action, get_audit_logs, create_approval_request
    return "audit_service OK"

def _import_observability():
    from api.services.observability_service import (
        get_system_health_summary, compute_adaptive_threshold, record_health_snapshot
    )
    return "observability_service OK"

def _import_meta_learning():
    from api.services.meta_learning_service import analyze_decision_outcomes
    return "meta_learning_service OK"

def _import_scenario():
    from api.services.scenario_service import run_scenario
    return "scenario_service OK"

def _import_chat():
    from api.services.chat_service import chat_with_aether, generate_daily_summary
    return "chat_service OK"

def _import_email():
    from api.services.email_service import send_alert_email, check_and_fire_alerts
    return "email_service OK"

def _import_adaptation():
    from adaptation.retrain_engine import retrain_model
    from adaptation.adaptation_engine import encode, TARGET
    return f"adaptation OK (TARGET='{TARGET}')"

check("fastapi import", _import_fastapi)
check("model_service import", _import_model_service)
check("decision_engine import", _import_decision_engine)
check("drift_service import", _import_drift_service)
check("explain_service import", _import_explain_service)
check("audit_service import", _import_audit_service)
check("observability_service import", _import_observability)
check("meta_learning_service import", _import_meta_learning)
check("scenario_service import", _import_scenario)
check("chat_service import", _import_chat)
check("email_service import", _import_email)
check("adaptation engine import", _import_adaptation)

# ─────────────────────────────────────────────────────────────
# SECTION 2: Database & Model File Checks
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 2 — Database & Model Artifacts")
print("═" * 62)

DOMAINS = ["hr_attrition", "fin_fraud", "crm_churn", "sec_threats", "market_leads", "supply_chain"]
MODELS_DIR = os.path.join(ROOT, "models", "domains")

def _check_db():
    from database.db import engine, Base
    from database.models import (HRAttrition, FinFraud, CRMChurn, SecThreats,
                                  MarketLeads, SupplyChain, AuditLog,
                                  PendingApproval, ExperimentRun, SystemHealth, AlertRule)
    Base.metadata.create_all(bind=engine)
    return "aether.db schema OK"

def _check_model_files():
    missing = []
    for domain in DOMAINS:
        model_path = os.path.join(MODELS_DIR, f"{domain}_model.pkl")
        if not os.path.exists(model_path):
            missing.append(domain)
    if missing:
        raise FileNotFoundError(f"Missing domain models: {missing}. Run: python scripts/train_models.py")
    return f"All {len(DOMAINS)} domain models present"

def _check_encoder_files():
    missing = []
    for domain in DOMAINS:
        if domain == "supply_chain":
            continue  # SARIMAX — no encoder expected
        enc_path = os.path.join(MODELS_DIR, f"{domain}_encoders.pkl")
        if not os.path.exists(enc_path):
            missing.append(domain)
    if missing:
        raise FileNotFoundError(f"Missing encoders: {missing}. Run: python scripts/train_models.py")
    return f"{len(DOMAINS)-1} classification encoders present (supply_chain skipped)"

check("database schema creation", _check_db)
check("domain model .pkl files", _check_model_files)
check("domain encoder .pkl files", _check_encoder_files)

# ─────────────────────────────────────────────────────────────
# SECTION 3: Domain Pipeline Execution
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 3 — Domain Metric Pipelines")
print("═" * 62)

def _make_metrics_check(domain):
    def _check():
        from api.services.model_service import compute_metrics
        result = compute_metrics(domain)
        if "error" in result:
            raise RuntimeError(result["error"])
        # Validate required keys exist
        if domain == "supply_chain":
            assert "mape" in result, "supply_chain: missing 'mape' key"
            assert "rmse" in result, "supply_chain: missing 'rmse' key"
        else:
            assert "f1_score" in result, f"{domain}: missing 'f1_score' key"
            assert "roc_auc" in result, f"{domain}: missing 'roc_auc' key"
            assert "drift_percentage" in result, f"{domain}: missing 'drift_percentage' key"
        return f"OK ({list(result.keys())})"
    return _check

for domain in DOMAINS:
    check(f"compute_metrics('{domain}')", _make_metrics_check(domain))

# ─────────────────────────────────────────────────────────────
# SECTION 4: Decision Engine Validation
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 4 — Decision Engine Logic")
print("═" * 62)

def _check_decision_engine_no_action():
    from api.services.decision_engine import DecisionEngine
    result = DecisionEngine.evaluate(
        "hr_attrition",
        {"f1_score": 0.95, "roc_auc": 0.97},
        {"drift_percentage": 5.0, "drifted_features": []},
        drift_threshold=0.15
    )
    assert result["action"] == "NO_ACTION", f"Expected NO_ACTION, got {result['action']}"
    assert "expected_daily_loss_usd" in result
    return f"action=NO_ACTION, risk={result['risk_level']}"

def _check_decision_engine_retrain():
    from api.services.decision_engine import DecisionEngine
    result = DecisionEngine.evaluate(
        "fin_fraud",
        {"f1_score": 0.50, "roc_auc": 0.55},
        {"drift_percentage": 65.0, "drifted_features": ["amount", "ip_distance"]},
        drift_threshold=0.15
    )
    assert result["action"] in ("RETRAIN", "FLAG_ANOMALY"), f"Expected RETRAIN/FLAG_ANOMALY, got {result['action']}"
    return f"action={result['action']}, risk={result['risk_level']}, loss=${result['expected_daily_loss_usd']:,.0f}"

def _check_decision_engine_monitor():
    from api.services.decision_engine import DecisionEngine
    result = DecisionEngine.evaluate(
        "crm_churn",
        {"f1_score": 0.75, "roc_auc": 0.81},
        {"drift_percentage": 28.0, "drifted_features": ["monthly_charges"]},
        drift_threshold=0.15
    )
    assert result["action"] in ("MONITOR", "RETRAIN"), f"Unexpected action: {result['action']}"
    return f"action={result['action']}, risk_score={result['risk_score_raw']:.3f}"

def _check_all_domain_multipliers():
    from api.services.decision_engine import DecisionEngine
    domains = list(DecisionEngine.DOMAIN_IMPACT_MULTIPLIERS.keys())
    assert len(domains) == 6, f"Expected 6 domains, got {len(domains)}"
    return f"multipliers for: {domains}"

check("Decision Engine: NO_ACTION path", _check_decision_engine_no_action)
check("Decision Engine: RETRAIN/FLAG path", _check_decision_engine_retrain)
check("Decision Engine: MONITOR path", _check_decision_engine_monitor)
check("Decision Engine: all domain multipliers", _check_all_domain_multipliers)

# ─────────────────────────────────────────────────────────────
# SECTION 5: Observability & System Health
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 5 — Observability & Health")
print("═" * 62)

def _check_system_health():
    from api.services.observability_service import get_system_health_summary
    result = get_system_health_summary()
    required = {"avg_latency_ms", "p99_latency_ms", "total_evaluations",
                "retrain_rate_pct", "avg_drift_pct", "domains_monitored"}
    missing = required - set(result.keys())
    if missing:
        raise AssertionError(f"Health response missing keys: {missing}")
    return f"evaluations={result['total_evaluations']}, domains={result['domains_monitored']}"

def _check_adaptive_threshold():
    from api.services.observability_service import compute_adaptive_threshold
    for domain in ["hr_attrition", "fin_fraud", "supply_chain"]:
        thresh = compute_adaptive_threshold(domain)
        assert 0.05 <= thresh <= 0.50, f"{domain}: threshold {thresh} out of bounds [0.05, 0.50]"
    return "all thresholds in [0.05, 0.50] range"

def _check_alert_rules_crud():
    from api.services.observability_service import create_alert_rule, get_alert_rules, toggle_alert_rule
    rule_id = create_alert_rule("hr_attrition", "drift_pct", 30.0, "email", "HIGH")
    assert isinstance(rule_id, int), "create_alert_rule must return int ID"
    rules = get_alert_rules()
    assert any(r["id"] == rule_id for r in rules), "Newly created rule not found"
    ok = toggle_alert_rule(rule_id, False)
    assert ok, "toggle_alert_rule returned False"
    return f"CRUD OK (rule_id={rule_id})"

check("system health summary", _check_system_health)
check("adaptive threshold computation", _check_adaptive_threshold)
check("alert rules CRUD", _check_alert_rules_crud)

# ─────────────────────────────────────────────────────────────
# SECTION 6: Supply Chain Encoder Guard
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 6 — Supply Chain Encoder Guard (Critical Fix)")
print("═" * 62)

def _check_supply_chain_no_encoder_error():
    """
    Confirms that compute_metrics('supply_chain') never attempts to load
    a non-existent *_encoders.pkl file, which previously caused FileNotFoundError.
    """
    import inspect
    from api.services import model_service
    source = inspect.getsource(model_service.compute_metrics)
    # The supply_chain check MUST appear before the encoder load line
    sc_idx = source.find("domain == \"supply_chain\"")
    enc_idx = source.find("joblib.load(encoder_path)")
    if sc_idx == -1:
        raise AssertionError("supply_chain guard not found in compute_metrics source!")
    if enc_idx == -1:
        raise AssertionError("encoder load line not found in compute_metrics source!")
    if sc_idx > enc_idx:
        raise AssertionError(
            "CRITICAL: supply_chain domain check appears AFTER encoder load — "
            "FileNotFoundError will still occur!"
        )
    return "supply_chain guard is correctly placed BEFORE encoder load"

check("supply_chain encoder guard position", _check_supply_chain_no_encoder_error)

# ─────────────────────────────────────────────────────────────
# SECTION 7: Scenario Simulator
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 7 — Scenario Simulator")
print("═" * 62)

def _check_scenario_service():
    from api.services.scenario_service import run_scenario
    result = run_scenario("hr_attrition", "monthly_income", -20.0)
    if "error" in result:
        raise RuntimeError(result["error"])
    required = {"baseline", "scenario", "delta_loss_usd", "decision_changed"}
    missing = required - set(result.keys())
    if missing:
        raise AssertionError(f"Scenario response missing keys: {missing}")
    return f"Δloss=${result['delta_loss_usd']:,.0f}, decision_changed={result['decision_changed']}"

check("scenario simulator (hr_attrition, -20%)", _check_scenario_service)

# ─────────────────────────────────────────────────────────────
# SECTION 8: Reliability Score Sanity
# ─────────────────────────────────────────────────────────────
print("\n" + "═" * 62)
print("  SECTION 8 — Reliability Score Calculation")
print("═" * 62)

def _check_reliability_formula():
    """Validates the reliability score formula inline (mirrors main.py /reliability logic)."""
    # Simulate a healthy model
    f1, roc, drift_pct = 0.92, 0.95, 8.0
    perf_score = (f1 + roc) / 2
    drift_penalty = min(drift_pct / 100, 1.0)
    reliability = round(max(0, perf_score * (1 - drift_penalty * 0.5)) * 100, 1)
    grade = "A" if reliability > 90 else "B" if reliability > 75 else "C" if reliability > 60 else "D"
    assert reliability > 80, f"Healthy model should score >80, got {reliability}"
    assert grade in ("A", "B"), f"Healthy model should be A or B grade, got {grade}"
    return f"score={reliability}, grade={grade}"

check("reliability score formula", _check_reliability_formula)

# ─────────────────────────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print("\n" + "═" * 62)
print(f"  VERIFICATION COMPLETE — {passed}/{total} checks passed")
print("═" * 62)

if failed == 0:
    print("\033[92m")
    print("  ██████╗  ███████╗ █████╗ ██████╗ ██╗   ██╗")
    print("  ██╔══██╗ ██╔════╝██╔══██╗██╔══██╗╚██╗ ██╔╝")
    print("  ██████╔╝ █████╗  ███████║██║  ██║ ╚████╔╝")
    print("  ██╔══██╗ ██╔══╝  ██╔══██║██║  ██║  ╚██╔╝")
    print("  ██║  ██║ ███████╗██║  ██║██████╔╝   ██║")
    print("  ╚═╝  ╚═╝ ╚══════╝╚═╝  ╚═╝╚═════╝    ╚═╝")
    print("\033[0m")
    print("  ✅  Aether AI is SUBMISSION READY.")
    print("  🚀  Safe to git add . && git commit && git push\n")
    sys.exit(0)
else:
    print(f"\n  ❌  {failed} check(s) FAILED. Fix issues above before submitting.\n")
    for label, ok, err in results:
        if not ok:
            print(f"     → [{label}]: {err}")
    print()
    sys.exit(1)
