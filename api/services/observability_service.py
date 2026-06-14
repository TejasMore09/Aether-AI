"""
Section 6.1: Experiment Tracking
Section 4.1: System Health Metrics
Section 10.2: Adaptive Thresholding
"""
import json
import time
from datetime import datetime
from database.db import SessionLocal, engine
from database.models import ExperimentRun, SystemHealth, AlertRule
import numpy as np


# ── EXPERIMENT TRACKING ──────────────────────────────────────────────────────

def log_experiment(
    domain: str,
    model_type: str,
    hyperparams: dict,
    metrics: dict,
    dataset_window: str = "2022-2023",
    notes: str = ""
):
    db = SessionLocal()
    try:
        run = ExperimentRun(
            timestamp=datetime.utcnow(),
            domain=domain,
            model_type=model_type,
            hyperparams=json.dumps(hyperparams),
            metrics=json.dumps(metrics),
            dataset_window=dataset_window,
            notes=notes
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def get_experiments(domain: str = None, limit: int = 50) -> list:
    db = SessionLocal()
    try:
        q = db.query(ExperimentRun).order_by(ExperimentRun.timestamp.desc())
        if domain:
            q = q.filter(ExperimentRun.domain == domain)
        runs = q.limit(limit).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "domain": r.domain,
                "model_type": r.model_type,
                "hyperparams": json.loads(r.hyperparams or "{}"),
                "metrics": json.loads(r.metrics or "{}"),
                "dataset_window": r.dataset_window,
                "notes": r.notes
            }
            for r in runs
        ]
    finally:
        db.close()


# ── SYSTEM HEALTH ─────────────────────────────────────────────────────────────

def record_health_snapshot(domain: str, latency_ms: float, drift_pct: float, action: str):
    db = SessionLocal()
    try:
        snap = SystemHealth(
            timestamp=datetime.utcnow(),
            domain=domain,
            latency_ms=latency_ms,
            drift_pct=drift_pct,
            action=action
        )
        db.add(snap)
        db.commit()
    finally:
        db.close()


def get_system_health_summary() -> dict:
    db = SessionLocal()
    try:
        recent = db.query(SystemHealth).order_by(SystemHealth.timestamp.desc()).limit(200).all()
        if not recent:
            return {
                "avg_latency_ms": 0, "p99_latency_ms": 0,
                "total_evaluations": 0, "retrain_rate_pct": 0,
                "avg_drift_pct": 0, "domains_monitored": 0
            }
        latencies = [r.latency_ms for r in recent if r.latency_ms]
        drifts = [r.drift_pct for r in recent if r.drift_pct is not None]
        retrains = sum(1 for r in recent if r.action == "RETRAIN")
        return {
            "avg_latency_ms": round(float(np.mean(latencies)), 1) if latencies else 0,
            "p99_latency_ms": round(float(np.percentile(latencies, 99)), 1) if latencies else 0,
            "total_evaluations": len(recent),
            "retrain_rate_pct": round(retrains / max(len(recent), 1) * 100, 1),
            "avg_drift_pct": round(float(np.mean(drifts)), 2) if drifts else 0,
            "domains_monitored": len(set(r.domain for r in recent))
        }
    finally:
        db.close()


# ── ALERT RULES ───────────────────────────────────────────────────────────────

def create_alert_rule(domain: str, metric: str, threshold: float, channel: str, severity: str = "HIGH") -> int:
    db = SessionLocal()
    try:
        rule = AlertRule(
            created_at=datetime.utcnow(),
            domain=domain,
            metric=metric,
            threshold=threshold,
            channel=channel,
            severity=severity,
            enabled=True
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule.id
    finally:
        db.close()


def get_alert_rules() -> list:
    db = SessionLocal()
    try:
        rules = db.query(AlertRule).order_by(AlertRule.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "domain": r.domain,
                "metric": r.metric,
                "threshold": r.threshold,
                "channel": r.channel,
                "severity": r.severity,
                "enabled": r.enabled,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in rules
        ]
    finally:
        db.close()


def toggle_alert_rule(rule_id: int, enabled: bool) -> bool:
    db = SessionLocal()
    try:
        rule = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
        if not rule:
            return False
        rule.enabled = enabled
        db.commit()
        return True
    finally:
        db.close()


# ── ADAPTIVE THRESHOLDING (10.2) ─────────────────────────────────────────────

def compute_adaptive_threshold(domain: str, base_threshold: float = 0.15) -> float:
    """
    Section 10.2: Adaptive Thresholding
    Adjusts drift threshold based on historical average drift patterns for the domain.
    If the domain historically has higher drift, the threshold adapts upward (less sensitive).
    If historically stable, it tightens (more sensitive).
    """
    db = SessionLocal()
    try:
        history = db.query(SystemHealth)\
            .filter(SystemHealth.domain == domain)\
            .order_by(SystemHealth.timestamp.desc())\
            .limit(30).all()

        if len(history) < 5:
            return base_threshold  # Not enough history, use base

        drifts = [h.drift_pct for h in history if h.drift_pct is not None]
        if not drifts:
            return base_threshold

        hist_avg = float(np.mean(drifts))
        hist_std = float(np.std(drifts))

        # Adaptive: base + 1 standard deviation of historical drift
        adaptive = round(base_threshold + (hist_std * 0.5), 3)
        # Clamp between 5% and 50%
        return float(np.clip(adaptive, 0.05, 0.50))
    finally:
        db.close()
