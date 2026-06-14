class DecisionEngine:
    """
    Core System Layer 1.1 & 1.2, Business Intelligence 2.2 & 2.3
    Evaluates ML performance, drift, and business logic to recommend an action.
    """
    
    # Financial constants for cost-aware reasoning
    RETRAIN_COMPUTE_COST_USD = 50.0  # Cost to spin up cloud GPUs
    
    DOMAIN_IMPACT_MULTIPLIERS = {
        "hr_attrition": 15000,   # Cost of an employee leaving
        "fin_fraud": 5000,       # Average fraud transaction loss
        "crm_churn": 1200,       # LTV of a lost customer
        "sec_threats": 50000,    # Cost of a minor breach
        "market_leads": 500,     # Lost conversion value
        "supply_chain": 25000    # Stockout / overstock cost
    }

    @staticmethod
    def evaluate(domain: str, metrics: dict, drift: dict, drift_threshold: float = 0.15) -> dict:
        """
        Determines the optimal system action based on multi-signal risk scoring.
        Uses adaptive threshold if provided (Section 10.2).
        """
        drift_pct = drift.get("drift_percentage", 0)
        
        # Use MAPE for supply chain, F1 for classification
        is_ts = domain == "supply_chain"
        if is_ts:
            perf_metric = metrics.get("mape", 0)
            perf_threshold = 5.0
            perf_degradation = max(0, perf_metric - perf_threshold) / perf_threshold
        else:
            perf_metric = metrics.get("f1_score", 1.0)
            perf_threshold = 0.85
            perf_degradation = max(0, perf_threshold - perf_metric) / perf_threshold
            
        # 1. Risk Scoring System (2.2) — uses adaptive threshold
        risk_score = 0.0
        risk_level = "LOW"
        
        if drift_pct > (drift_threshold * 100):
            risk_score += (drift_pct / 100) * 0.4
        if perf_degradation > 0:
            risk_score += perf_degradation * 0.6
            
        if risk_score > 0.4:
            risk_level = "HIGH"
        elif risk_score > 0.15:
            risk_level = "MEDIUM"
            
        # 2. Business Impact Estimator (2.1)
        # Estimate how many bad decisions the degradation causes per day
        daily_volume_estimate = 1000 
        error_rate_increase = perf_degradation * 0.1 # 10% translation
        
        expected_daily_loss = daily_volume_estimate * error_rate_increase * DecisionEngine.DOMAIN_IMPACT_MULTIPLIERS.get(domain, 1000)
        
        # 3. Cost-Aware Decision Logic (2.3)
        action = "NO_ACTION"
        reason = "System operating within acceptable bounds."
        
        if risk_level == "HIGH":
            if expected_daily_loss > DecisionEngine.RETRAIN_COMPUTE_COST_USD:
                action = "RETRAIN"
                reason = f"High risk detected. Expected daily loss (${expected_daily_loss:,.2f}) outweighs retraining cost (${DecisionEngine.RETRAIN_COMPUTE_COST_USD:,.2f})."
            else:
                action = "FLAG_ANOMALY"
                reason = f"High risk detected, but expected loss (${expected_daily_loss:,.2f}) does not justify retraining compute cost."
        elif risk_level == "MEDIUM":
            action = "MONITOR"
            reason = "Medium risk detected. Placing model under elevated observation."
            
        return {
            "action": action,
            "risk_level": risk_level,
            "risk_score_raw": float(risk_score),
            "expected_daily_loss_usd": float(expected_daily_loss),
            "retraining_cost_usd": DecisionEngine.RETRAIN_COMPUTE_COST_USD,
            "reason": reason
        }
