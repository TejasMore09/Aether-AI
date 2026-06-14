import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import sys

# Add root to sys path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from database.db import engine, Base, SessionLocal
from database.models import HRAttrition, FinFraud, CRMChurn, SecThreats, MarketLeads, SupplyChain

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

def generate_timestamps(n, start_year=2022, end_year=2024):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    diff = end - start
    return [start + timedelta(days=np.random.randint(0, diff.days), 
                              seconds=np.random.randint(0, 86400)) 
            for _ in range(n)]

def process_hr(db: Session, n_samples=5000):
    print("Processing HR Attrition...")
    df = pd.read_csv(os.path.join(BASE_DIR, "datasets", "IBM HR Data new.csv"), low_memory=False)
    df = df.sample(n=min(n_samples, len(df)), random_state=42)
    
    # Coerce to numeric
    df['MonthlyIncome'] = pd.to_numeric(df['MonthlyIncome'], errors='coerce').fillna(0)
    df['Age'] = pd.to_numeric(df['Age'], errors='coerce').fillna(0)
    df['DistanceFromHome'] = pd.to_numeric(df['DistanceFromHome'], errors='coerce').fillna(0)
    df['PerformanceRating'] = pd.to_numeric(df['PerformanceRating'], errors='coerce').fillna(0)
    
    # Map and synthesize
    df['attrition_int'] = df['Attrition'].apply(lambda x: 1 if x == 'Voluntary Resignation' or x == 'Yes' else 0)
    df['workload'] = np.random.uniform(30, 100, size=len(df))
    # Inject signal: high workload + low income = higher attrition
    mask = (df['workload'] > 80) & (df['MonthlyIncome'] < 5000)
    df.loc[mask, 'attrition_int'] = np.random.choice([0, 1], p=[0.2, 0.8], size=mask.sum())
    
    timestamps = generate_timestamps(len(df))
    
    records = []
    for i, row in enumerate(df.itertuples()):
        record = HRAttrition(
            age=int(row.Age),
            department=str(row.Department),
            distance_from_home=int(row.DistanceFromHome),
            monthly_income=float(row.MonthlyIncome),
            performance_rating=int(row.PerformanceRating),
            workload=float(row.workload),
            attrition=int(row.attrition_int),
            timestamp=timestamps[i]
        )
        records.append(record)
    
    db.add_all(records)
    db.commit()

def process_fraud(db: Session, n_samples=5000):
    print("Processing Financial Fraud...")
    df = pd.read_csv(os.path.join(BASE_DIR, "datasets", "credit_card_fraud_dataset.csv"), low_memory=False)
    df = df.sample(n=min(n_samples, len(df)), random_state=42)
    
    df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
    df['IsFraud'] = pd.to_numeric(df['IsFraud'], errors='coerce').fillna(0)
    
    df['ip_distance'] = np.random.uniform(0, 5000, size=len(df))
    # Signal: high ip distance = higher fraud
    mask = df['ip_distance'] > 4000
    df.loc[mask, 'IsFraud'] = np.random.choice([0, 1], p=[0.3, 0.7], size=mask.sum())
    
    timestamps = generate_timestamps(len(df))
    
    records = []
    for i, row in enumerate(df.itertuples()):
        record = FinFraud(
            amount=float(row.Amount),
            merchant_id=str(row.MerchantID),
            transaction_type=str(row.TransactionType),
            location=str(row.Location),
            ip_distance=float(row.ip_distance),
            is_fraud=int(row.IsFraud),
            timestamp=timestamps[i]
        )
        records.append(record)
    
    db.add_all(records)
    db.commit()

def process_crm(db: Session, n_samples=5000):
    print("Processing CRM Churn...")
    df = pd.read_csv(os.path.join(BASE_DIR, "datasets", "Telco_customer_churn.csv"), low_memory=False)
    df = df.sample(n=min(n_samples, len(df)), random_state=42)
    
    # Handle missing/empty numeric columns
    df['TotalCharges'] = pd.to_numeric(df['TotalCharges'].replace(' ', np.nan), errors='coerce').fillna(0)
    df['MonthlyCharges'] = pd.to_numeric(df['MonthlyCharges'], errors='coerce').fillna(0)
    df['tenure'] = pd.to_numeric(df['tenure'], errors='coerce').fillna(0)
    
    df['churn_int'] = df['Churn'].apply(lambda x: 1 if x == 'Yes' else 0)
    df['support_tickets'] = np.random.randint(0, 10, size=len(df))
    # Signal: more tickets + low tenure = churn
    mask = (df['support_tickets'] > 5) & (df['tenure'] < 12)
    df.loc[mask, 'churn_int'] = np.random.choice([0, 1], p=[0.1, 0.9], size=mask.sum())
    
    timestamps = generate_timestamps(len(df))
    
    records = []
    for i, row in enumerate(df.itertuples()):
        record = CRMChurn(
            tenure=int(row.tenure),
            monthly_charges=float(row.MonthlyCharges),
            total_charges=float(row.TotalCharges),
            contract_type=str(row.Contract),
            support_tickets=int(row.support_tickets),
            churn=int(row.churn_int),
            timestamp=timestamps[i]
        )
        records.append(record)
    
    db.add_all(records)
    db.commit()

def process_sec(db: Session, n_samples=5000):
    print("Processing Security Threats...")
    df = pd.read_csv(os.path.join(BASE_DIR, "datasets", "cybersecurity_intrusion_data.csv"), low_memory=False)
    df = df.sample(n=min(n_samples, len(df)), random_state=42)
    
    df['session_duration'] = pd.to_numeric(df['session_duration'], errors='coerce').fillna(0)
    df['login_attempts'] = pd.to_numeric(df['login_attempts'], errors='coerce').fillna(0)
    df['failed_logins'] = pd.to_numeric(df['failed_logins'], errors='coerce').fillna(0)
    df['ip_reputation_score'] = pd.to_numeric(df['ip_reputation_score'], errors='coerce').fillna(0)
    df['attack_detected'] = pd.to_numeric(df['attack_detected'], errors='coerce').fillna(0)
    
    df['bandwidth_spikes'] = np.random.uniform(10, 1000, size=len(df))
    # Signal
    mask = (df['failed_logins'] > 3) & (df['bandwidth_spikes'] > 800)
    df.loc[mask, 'attack_detected'] = np.random.choice([0, 1], p=[0.05, 0.95], size=mask.sum())
    
    timestamps = generate_timestamps(len(df))
    
    records = []
    for i, row in enumerate(df.itertuples()):
        record = SecThreats(
            session_duration=float(row.session_duration),
            protocol_type=str(row.protocol_type),
            login_attempts=int(row.login_attempts),
            failed_logins=int(row.failed_logins),
            ip_reputation_score=float(row.ip_reputation_score),
            bandwidth_spikes=float(row.bandwidth_spikes),
            attack_detected=int(row.attack_detected),
            timestamp=timestamps[i]
        )
        records.append(record)
    
    db.add_all(records)
    db.commit()

def process_market(db: Session, n_samples=5000):
    print("Synthesizing Market Leads...")
    
    session_duration = np.random.exponential(scale=120, size=n_samples)
    pages_visited = np.random.poisson(lam=4, size=n_samples)
    cart_value = np.random.uniform(0, 500, size=n_samples)
    engagement_score = (session_duration / 60) * pages_visited
    
    # Calculate conversion probability
    prob = 1 / (1 + np.exp(-(engagement_score * 0.1 - 2)))
    conversion = np.random.binomial(1, p=np.clip(prob, 0, 1))
    
    timestamps = generate_timestamps(n_samples)
    
    records = []
    for i in range(n_samples):
        record = MarketLeads(
            session_duration=float(session_duration[i]),
            pages_visited=int(pages_visited[i]),
            cart_value=float(cart_value[i]),
            engagement_score=float(engagement_score[i]),
            conversion=int(conversion[i]),
            timestamp=timestamps[i]
        )
        records.append(record)
    
    db.add_all(records)
    db.commit()

def process_supply_chain(db: Session):
    print("Synthesizing Supply Chain Time Series...")
    # Generate daily data from 2022 to 2024
    start_date = datetime(2022, 1, 1)
    days = (datetime(2024, 12, 31) - start_date).days + 1
    
    records = []
    # Base demand + trend + seasonality + noise
    base = 500
    for day in range(days):
        current_date = start_date + timedelta(days=day)
        trend = day * 0.5
        seasonality = 200 * np.sin(2 * np.pi * day / 365.25)
        noise = np.random.normal(0, 50)
        demand = max(0, base + trend + seasonality + noise)
        
        record = SupplyChain(
            product_id="SKU-899",
            demand_volume=demand,
            timestamp=current_date
        )
        records.append(record)
        
    db.add_all(records)
    db.commit()

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        # Clear existing data for a fresh start
        print("Clearing old data...")
        db.query(HRAttrition).delete()
        db.query(FinFraud).delete()
        db.query(CRMChurn).delete()
        db.query(SecThreats).delete()
        db.query(MarketLeads).delete()
        db.query(SupplyChain).delete()
        db.commit()

        process_hr(db)
        process_fraud(db)
        process_crm(db)
        process_sec(db)
        process_market(db)
        process_supply_chain(db)
        print("Database synthesis completed successfully!")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()
