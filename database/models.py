from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from database.db import Base
import datetime

class HRAttrition(Base):
    __tablename__ = 'hr_attrition'
    id = Column(Integer, primary_key=True, index=True)
    age = Column(Integer)
    department = Column(String)
    distance_from_home = Column(Integer)
    monthly_income = Column(Float)
    performance_rating = Column(Integer)
    workload = Column(Float)
    attrition = Column(Integer)
    timestamp = Column(DateTime, index=True)

class FinFraud(Base):
    __tablename__ = 'fin_fraud'
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float)
    merchant_id = Column(String)
    transaction_type = Column(String)
    location = Column(String)
    ip_distance = Column(Float)
    is_fraud = Column(Integer)
    timestamp = Column(DateTime, index=True)

class CRMChurn(Base):
    __tablename__ = 'crm_churn'
    id = Column(Integer, primary_key=True, index=True)
    tenure = Column(Integer)
    monthly_charges = Column(Float)
    total_charges = Column(Float)
    contract_type = Column(String)
    support_tickets = Column(Integer)
    churn = Column(Integer)
    timestamp = Column(DateTime, index=True)

class SecThreats(Base):
    __tablename__ = 'sec_threats'
    id = Column(Integer, primary_key=True, index=True)
    session_duration = Column(Float)
    protocol_type = Column(String)
    login_attempts = Column(Integer)
    failed_logins = Column(Integer)
    ip_reputation_score = Column(Float)
    bandwidth_spikes = Column(Float)
    attack_detected = Column(Integer)
    timestamp = Column(DateTime, index=True)

class MarketLeads(Base):
    __tablename__ = 'market_leads'
    id = Column(Integer, primary_key=True, index=True)
    session_duration = Column(Float)
    pages_visited = Column(Integer)
    cart_value = Column(Float)
    engagement_score = Column(Float)
    conversion = Column(Integer)
    timestamp = Column(DateTime, index=True)

class SupplyChain(Base):
    __tablename__ = 'supply_chain'
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String)
    demand_volume = Column(Float)
    timestamp = Column(DateTime, index=True)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    domain = Column(String, index=True)
    action = Column(String)          # RETRAIN, FLAG_ANOMALY, MONITOR, NO_ACTION
    triggered_by = Column(String)    # system | user
    risk_level = Column(String)      # LOW | MEDIUM | HIGH
    drift_pct = Column(Float)
    f1_before = Column(Float)
    expected_loss_usd = Column(Float)
    details = Column(String)         # JSON string for extra context
    status = Column(String, default='completed')  # completed | pending | approved | rejected

class PendingApproval(Base):
    __tablename__ = 'pending_approvals'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    domain = Column(String, index=True)
    action = Column(String)
    reason = Column(String)
    risk_level = Column(String)
    expected_loss_usd = Column(Float)
    status = Column(String, default='pending')  # pending | approved | rejected

class ExperimentRun(Base):
    __tablename__ = 'experiment_runs'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True, default=datetime.datetime.utcnow)
    domain = Column(String, index=True)
    model_type = Column(String)        # XGBoost | SARIMAX
    hyperparams = Column(String)       # JSON
    metrics = Column(String)           # JSON
    dataset_window = Column(String)    # e.g. 2022-2023
    notes = Column(String, default='')

class SystemHealth(Base):
    __tablename__ = 'system_health'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, index=True, default=datetime.datetime.utcnow)
    domain = Column(String, index=True)
    latency_ms = Column(Float)
    drift_pct = Column(Float)
    action = Column(String)            # Last Decision Engine action

class AlertRule(Base):
    __tablename__ = 'alert_rules'
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    domain = Column(String, index=True)
    metric = Column(String)            # drift_pct | f1_score | expected_loss
    threshold = Column(Float)
    channel = Column(String)           # email | slack | webhook
    severity = Column(String)          # LOW | MEDIUM | HIGH
    enabled = Column(Boolean, default=True)
