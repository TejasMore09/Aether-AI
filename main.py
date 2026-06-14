# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import joblib
import os
import time
from sklearn.metrics import f1_score, roc_auc_score

from features.build_features import build_features
from api.services.drift_service import detect_drift
from api.services.model_service import compute_metrics
from api.services.decision_engine import DecisionEngine
from api.services.explain_service import generate_ai_explanation
from api.services.version_service import save_version, get_versions
from api.services.audit_service import (
    log_action, get_audit_logs,
    create_approval_request, get_pending_approvals, resolve_approval
)
from api.services.scenario_service import run_scenario
from api.services.chat_service import chat_with_aether, generate_daily_summary
from api.services.observability_service import (
    log_experiment, get_experiments,
    record_health_snapshot, get_system_health_summary,
    create_alert_rule, get_alert_rules, toggle_alert_rule,
    compute_adaptive_threshold
)
from api.services.meta_learning_service import analyze_decision_outcomes
from api.services.email_service import send_alert_email, check_and_fire_alerts
from api.services.vector_store_service import (
    initialize_vector_store,
    semantic_lookup,
    get_index_stats,
    format_context_block,
    rebuild_index,
)
from database.db import engine
from database.models import Base
import numpy as np
import time

# Create all DB tables on startup
Base.metadata.create_all(bind=engine)

def _seed_health_data():
    """Run decision engine for all domains on startup to populate System Health."""
    ALL_DOMAINS = ["hr_attrition", "fin_fraud", "crm_churn", "sec_threats", "market_leads"]
    for d in ALL_DOMAINS:
        try:
            t0 = time.time()
            m = compute_metrics(d)
            dr = {"drift_percentage": m.get("drift_percentage", 0), "drifted_features": m.get("drifted_features", [])}
            thresh = compute_adaptive_threshold(d)
            dec = DecisionEngine.evaluate(d, m, dr, thresh)
            record_health_snapshot(
                domain=d,
                latency_ms=round((time.time() - t0) * 1000, 1),
                drift_pct=dr["drift_percentage"],
                action=dec["action"]
            )
        except Exception:
            pass

_seed_health_data()

# ------------ Build RAG telemetry vector store on startup ----------------
try:
    _vs_doc_count = initialize_vector_store()
    print(f"[Aether RAG] Vector store ready — {_vs_doc_count} documents indexed.")
except Exception as _vs_err:
    print(f"[Aether RAG] Vector store build skipped at startup: {_vs_err}")

app = FastAPI(title="Adaptive AI System API")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Load model ----------------
model = joblib.load("models/baseline_xgb.pkl")
encoders = joblib.load("models/encoders.pkl")

windows = [
    "data/processed/window1.csv",
    "data/processed/window2.csv",
    "data/processed/window3.csv",
    "data/processed/window4.csv",
]

# ---------------- Save baseline version once ----------------
versions = get_versions()

if len(versions) == 0:
    save_version(
        "v1.0-baseline",
        accuracy=0.49,
        latency=150,
        status="active"
    )

# ---------------- METRICS & DRIFT ----------------
@app.get("/metrics")
def get_metrics(domain: str = "hr_attrition"):
    return compute_metrics(domain)

@app.get("/drift")
def get_drift(domain: str = "hr_attrition"):
    metrics_data = compute_metrics(domain)
    if "error" in metrics_data:
        return metrics_data
        
    return {
        "drift_percentage": metrics_data.get("drift_percentage", 0),
        "drifted_features": metrics_data.get("drifted_features", []),
        "feature_impact": metrics_data.get("feature_impact", {})
    }

# ---------------- ADAPT ----------------
@app.get("/adapt")
def adapt_model():

    global model

    reference = build_features(pd.read_csv(windows[0]))
    current = build_features(pd.read_csv(windows[1]))

    drift_result = detect_drift(
        reference.drop(columns=[TARGET, "Hire_Date"]),
        current.drop(columns=[TARGET, "Hire_Date"]),
    )

    test = build_features(pd.read_csv(windows[1]))
    X = encode(test, encoders)
    y = test[TARGET]

    roc = roc_auc_score(y, model.predict_proba(X)[:, 1])

    should_adapt = roc < 0.5 or drift_result["drift_percentage"] > 30

    if should_adapt:

        start = time.time()

        new_model = retrain_model(windows, encoders)

        latency = int((time.time() - start) * 1000)

        version_name = f"v{int(time.time())}"

        os.makedirs("models/versions", exist_ok=True)

        path = f"models/versions/{version_name}.pkl"

        joblib.dump(new_model, path)

        model = new_model

        save_version(
            version_name,
            accuracy=roc,
            latency=latency,
            status="active"
        )

        return {
            "adapted": True,
            "new_version": version_name
        }

    return {"adapted": False}

# ---------------- MODEL VERSIONS ----------------
@app.get("/versions")
def model_versions():
    return get_versions()

# ---------------- DECISION ENGINE (with Audit Log + Health Tracking) ----------------
@app.get("/decision")
def get_decision(domain: str = "hr_attrition"):
    t0 = time.time()
    metrics = compute_metrics(domain)
    drift_data = get_drift(domain)
    
    # Adaptive Thresholding (10.2) — adjust risk threshold based on history
    adaptive_thresh = compute_adaptive_threshold(domain)
    decision = DecisionEngine.evaluate(domain, metrics, drift_data, adaptive_thresh)
    
    latency_ms = round((time.time() - t0) * 1000, 1)
    
    # Record health snapshot
    record_health_snapshot(
        domain=domain,
        latency_ms=latency_ms,
        drift_pct=drift_data.get("drift_percentage", 0),
        action=decision["action"]
    )
    
    # Governance: High-risk actions need human approval before executing
    if decision["action"] == "RETRAIN" and decision["risk_level"] == "HIGH":
        approval_id = create_approval_request(
            domain=domain,
            action="RETRAIN",
            reason=decision["reason"],
            risk_level=decision["risk_level"],
            expected_loss_usd=decision["expected_daily_loss_usd"]
        )
        decision["approval_required"] = True
        decision["approval_id"] = approval_id
        log_action(domain=domain, action="RETRAIN", triggered_by="system",
                   risk_level=decision["risk_level"],
                   drift_pct=drift_data.get("drift_percentage", 0),
                   f1_before=metrics.get("f1_score", 0),
                   expected_loss_usd=decision["expected_daily_loss_usd"],
                   status="pending")
    else:
        decision["approval_required"] = False
        log_action(domain=domain, action=decision["action"], triggered_by="system",
                   risk_level=decision["risk_level"],
                   drift_pct=drift_data.get("drift_percentage", 0),
                   f1_before=metrics.get("f1_score", 0),
                   expected_loss_usd=decision["expected_daily_loss_usd"])
    
    # Fire real email alerts if any rules are breached
    rules = get_alert_rules()
    drift_pct = drift_data.get("drift_percentage", 0)
    fired_alerts = check_and_fire_alerts(
        domain=domain,
        metric="drift_pct",
        value=drift_pct,
        rules=rules,
        decision=decision,
        drift=drift_data
    )
    if fired_alerts:
        decision["alerts_fired"] = fired_alerts
    
    decision["latency_ms"] = latency_ms
    decision["adaptive_threshold"] = adaptive_thresh
    return decision

# ---------------- RELIABILITY SCORE ----------------
@app.get("/reliability")
def get_reliability(domain: str = "hr_attrition"):
    """Section 2.5: Model Reliability Score - single trust indicator"""
    metrics = compute_metrics(domain)
    drift_data = get_drift(domain)
    
    drift_pct = drift_data.get("drift_percentage", 0)
    f1 = metrics.get("f1_score", 1.0)
    roc = metrics.get("roc_auc", 1.0)
    mape = metrics.get("mape", 0)
    
    is_ts = domain == "supply_chain"
    if is_ts:
        perf_score = max(0, 1 - (mape / 10))  # 0% MAPE = 100, 10% = 0
    else:
        perf_score = (f1 + roc) / 2 if roc else f1
    
    drift_penalty = min(drift_pct / 100, 1.0)
    reliability = round(max(0, perf_score * (1 - drift_penalty * 0.5)) * 100, 1)
    
    grade = "A" if reliability > 90 else "B" if reliability > 75 else "C" if reliability > 60 else "D"
    
    return {
        "domain": domain,
        "reliability_score": reliability,
        "grade": grade,
        "perf_score": round(float(perf_score) * 100, 1),
        "drift_penalty_pct": round(drift_penalty * 100, 1)
    }

# ---------------- AUDIT LOGS ----------------
@app.get("/audit-logs")
def audit_logs(domain: str = None, limit: int = 50):
    return get_audit_logs(domain=domain, limit=limit)

# ---------------- GOVERNANCE APPROVALS ----------------
@app.get("/approvals")
def approvals():
    return get_pending_approvals()

@app.post("/approvals/{approval_id}/resolve")
def resolve(approval_id: int, decision: str = "approved"):
    ok = resolve_approval(approval_id, decision)
    if ok:
        log_action(domain="governance", action=f"APPROVAL_{decision.upper()}",
                   triggered_by="user", risk_level="HIGH", status=decision)
    return {"success": ok}

# ---------------- SYSTEM HEALTH (4.1) ----------------
@app.get("/health")
def system_health():
    return get_system_health_summary()

# ---------------- ALERT RULES (4.2) ----------------
@app.get("/alerts")
def list_alerts():
    return get_alert_rules()

@app.post("/alerts")
def add_alert(domain: str, metric: str = "drift_pct", threshold: float = 30.0, channel: str = "email", severity: str = "HIGH"):
    rule_id = create_alert_rule(domain, metric, threshold, channel, severity)
    return {"id": rule_id, "message": f"Alert rule created for {domain}.{metric} > {threshold}"}

@app.post("/alerts/{rule_id}/toggle")
def toggle_alert(rule_id: int, enabled: bool = True):
    ok = toggle_alert_rule(rule_id, enabled)
    return {"success": ok}

@app.post("/send-test-alert")
def send_test_alert():
    """Sends a mock critical alert to verify email delivery."""
    result = send_alert_email(
        domain="fin_fraud",
        metric="drift_pct",
        value=42.5,
        threshold=30.0,
        action="RETRAIN",
        risk_level="HIGH",
        expected_loss_usd=12500.0,
        drift_features=["amount", "ip_distance"]
    )
    return result

# ---------------- EXPERIMENT TRACKING (6.1) ----------------
@app.get("/experiments")
def list_experiments(domain: str = None):
    return get_experiments(domain=domain)

# ---------------- ROLE-BASED EXPLAIN (3.1) ----------------
@app.get("/explain")
def explain(domain: str = "hr_attrition", role: str = "executive"):
    metrics = compute_metrics(domain)
    drift_data = get_drift(domain)
    decision = DecisionEngine.evaluate(domain, metrics, drift_data)
    explanation = generate_ai_explanation(domain, metrics, drift_data, decision, role=role)
    return {"explanation": explanation, "role": role}

# ---------------- ADAPTIVE THRESHOLD (10.2) ----------------
@app.get("/adaptive-threshold")
def adaptive_threshold(domain: str = "hr_attrition"):
    threshold = compute_adaptive_threshold(domain)
    return {"domain": domain, "adaptive_threshold": threshold}

# ---------------- META-LEARNING LOOP (10.1, 10.3, 10.4) ----------------
@app.get("/meta-learning")
def meta_learning(domain: str = None):
    return analyze_decision_outcomes(domain)

# ---------------- Simulate Drift ----------------

@app.post("/simulate-drift")
def simulate_drift(level: float = 2.5, domain: str = "hr_attrition"):
    import numpy as np
    from sqlalchemy import text
    from database.db import engine
    
    query = f"SELECT * FROM {domain} WHERE timestamp >= '2023-01-01' AND timestamp < '2024-01-01'"
    df = pd.read_sql(query, con=engine)
    
    if len(df) == 0:
        return {"error": "No 2023 data to drift"}
        
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for drop in ["id", "attrition", "is_fraud", "churn", "attack_detected", "conversion", "demand_volume"]:
        if drop in num_cols:
            num_cols.remove(drop)
            
    # Inject drift into numeric features
    for col in num_cols:
        std = df[col].std()
        if std > 0:
            df[col] = df[col] + np.random.normal(0, std * level, len(df))
            
    # Replace the corrupted window in the database
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {domain} WHERE timestamp >= '2023-01-01' AND timestamp < '2024-01-01'"))
    
    # We drop ID so SQLite auto-increments it properly on append
    if "id" in df.columns:
        df = df.drop(columns=["id"])
        
    df.to_sql(domain, con=engine, if_exists='append', index=False)

    return {
        "message": f"Drift injected at level {level} for {domain}"
    }

# ---------------- SCENARIO SIMULATOR (2.4) ----------------
@app.get("/scenario")
def scenario(domain: str = "hr_attrition", feature: str = "monthly_income", shift_pct: float = -20.0):
    result = run_scenario(domain, feature, shift_pct)
    if "error" not in result:
        log_action(domain=domain, action="SCENARIO_SIM", triggered_by="user",
                   risk_level=result["scenario"]["risk_level"],
                   drift_pct=result["scenario"]["drift_percentage"],
                   expected_loss_usd=result["scenario"]["expected_daily_loss_usd"],
                   details=result)
    return result

# ---------------- CONVERSATIONAL CHAT (7.2) ----------------
@app.post("/chat")
def chat(domain: str = "hr_attrition", question: str = "What is the model status?"):
    metrics = compute_metrics(domain)
    drift_data = get_drift(domain)
    decision = DecisionEngine.evaluate(domain, metrics, drift_data)
    context = {"metrics": metrics, "drift": drift_data, "decision": decision}
    answer = chat_with_aether(question, domain, context)
    return {"question": question, "answer": answer}

# ---------------- DAILY SUMMARY (7.3) ----------------
@app.get("/summary")
def daily_summary():
    DOMAINS = ["hr_attrition", "fin_fraud", "crm_churn", "sec_threats", "market_leads"]
    all_data = []
    for d in DOMAINS:
        try:
            metrics = compute_metrics(d)
            drift_data = get_drift(d)
            decision = DecisionEngine.evaluate(d, metrics, drift_data)
            all_data.append({
                "domain": d,
                "action": decision["action"],
                "risk_level": decision["risk_level"],
                "drift_pct": drift_data.get("drift_percentage", 0),
                "expected_loss": decision["expected_daily_loss_usd"]
            })
        except:
            pass
    summary = generate_daily_summary(all_data)
    return {"summary": summary, "domains": all_data}


# -------- RAG SEMANTIC DIAGNOSIS (v1 — elite engineering layer) ----------
@app.get("/api/v1/diagnosis/semantic-lookup")
def semantic_diagnosis(
    domain: str = "hr_attrition",
    metric: str = "drift_pct",
    top_k: int = 5,
    rebuild: bool = False,
):
    """
    Semantic RAG lookup against Aether AI's operational memory.

    Constructs a state-aware query from the domain's live telemetry,
    retrieves the top-k most historically similar MLOps events from the
    in-memory TF-IDF vector store, and returns a structured context block
    mapping analogous past incidents across all 6 business domains.

    Params:
        domain  -- Business domain to query (e.g. hr_attrition, fin_fraud)
        metric  -- Target metric framing the query (drift_pct | f1_score | expected_loss)
        top_k   -- Number of historical precedents to retrieve (1-20)
        rebuild -- If True, force-rebuilds the index before querying
    """
    top_k = max(1, min(top_k, 20))  # clamp to safe range

    # Optional index rebuild (e.g. after simulate-drift or new training run)
    if rebuild:
        try:
            count = rebuild_index()
            print(f"[Aether RAG] Index rebuilt on demand: {count} documents")
        except Exception as e:
            return {"error": f"Index rebuild failed: {e}"}

    # --- Pull live telemetry for query construction ---
    try:
        live_metrics = compute_metrics(domain)
        live_drift   = get_drift(domain)
    except Exception as e:
        return {"error": f"Could not fetch live telemetry for '{domain}': {e}"}

    if "error" in live_metrics:
        return live_metrics

    # --- Build the semantic query from current system state ---
    action_hint = ""
    if metric == "drift_pct":
        pct = live_drift.get("drift_percentage", 0)
        feats = " ".join(live_drift.get("drifted_features", []))
        action_hint = f"drift percentage {pct:.1f} percent drifted features {feats}"
    elif metric == "f1_score":
        action_hint = f"f1 score {live_metrics.get('f1_score', 0):.4f} model performance degradation"
    elif metric == "expected_loss":
        action_hint = "expected daily loss financial risk high drift"
    else:
        action_hint = f"domain {domain} {metric}"

    query_text = (
        f"domain {domain} "
        f"{action_hint} "
        f"roc auc {live_metrics.get('roc_auc', 0):.4f}"
    )

    # --- Query the vector store ---
    results = semantic_lookup(query_text, top_k=top_k, domain=domain)

    # --- Group results by source for structured output ---
    by_source: dict = {}
    for r in results:
        src = r.get("source", "unknown")
        by_source.setdefault(src, []).append({
            "domain":              r.get("domain"),
            "summary":             r.get("summary"),
            "similarity_score":    r.get("similarity_score"),
            "action":              r.get("action"),
            "risk_level":          r.get("risk_level"),
            "drift_pct":           r.get("drift_pct"),
            "f1_before":           r.get("f1_before"),
            "expected_loss_usd":   r.get("expected_loss_usd"),
            "timestamp":           r.get("timestamp"),
            "metrics":             r.get("metrics"),
            "model_type":          r.get("model_type"),
        })

    # --- Cross-domain pattern detection ---
    domains_in_results = list(set(r.get("domain") for r in results if r.get("domain") != domain))
    cross_domain_signal = (
        f"Similar historical patterns detected in: {', '.join(domains_in_results)}"
        if domains_in_results
        else "No significant cross-domain patterns found."
    )

    return {
        "domain":                domain,
        "metric_queried":        metric,
        "query_used":            query_text,
        "live_telemetry": {
            "drift_pct":         live_drift.get("drift_percentage", 0),
            "drifted_features":  live_drift.get("drifted_features", []),
            "f1_score":          live_metrics.get("f1_score"),
            "roc_auc":           live_metrics.get("roc_auc"),
        },
        "retrieved_precedents":  results,
        "precedents_by_source":  by_source,
        "cross_domain_signal":   cross_domain_signal,
        "formatted_context":     format_context_block(results),
        "index_stats":           get_index_stats(),
    }