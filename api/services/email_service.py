"""
Real Email Alert Service — Section 4.2
Sends actual emails via Gmail SMTP when alert thresholds are breached.
Requires GMAIL_SENDER + GMAIL_APP_PASSWORD in .env
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv


def _get_smtp_config():
    load_dotenv(override=True)
    return {
        "sender": os.environ.get("GMAIL_SENDER", ""),
        "password": os.environ.get("GMAIL_APP_PASSWORD", ""),
        "recipient": os.environ.get("ALERT_RECIPIENT", "tejasmore464@gmail.com"),
    }


def send_alert_email(
    domain: str,
    metric: str,
    value: float,
    threshold: float,
    action: str,
    risk_level: str,
    expected_loss_usd: float,
    drift_features: list = None,
) -> dict:
    """Send a real email alert to the configured recipient."""
    cfg = _get_smtp_config()

    if not cfg["sender"] or not cfg["password"]:
        return {"sent": False, "reason": "GMAIL_SENDER or GMAIL_APP_PASSWORD missing in .env"}

    domain_label = domain.replace("_", " ").title()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    features_html = ""
    if drift_features:
        features_html = "<ul>" + "".join(f"<li style='color:#ef4444'>{f}</li>" for f in drift_features) + "</ul>"
    else:
        features_html = "<p style='color:#22c55e'>No features drifted</p>"

    action_color = {"RETRAIN": "#ef4444", "MONITOR": "#eab308", "FLAG_ANOMALY": "#f97316", "NO_ACTION": "#22c55e"}.get(action, "#a3a3a3")
    risk_color = {"HIGH": "#ef4444", "MEDIUM": "#eab308", "LOW": "#22c55e"}.get(risk_level, "#a3a3a3")

    html_body = f"""
    <div style="background:#0a0a0a;color:#ffffff;font-family:monospace;padding:32px;max-width:640px;margin:auto;border:1px solid #262626;">
      <div style="border-bottom:2px solid {action_color};padding-bottom:16px;margin-bottom:24px;">
        <h1 style="margin:0;font-size:20px;color:#ffffff;">⚡ Aether AI Alert</h1>
        <p style="margin:4px 0 0;color:#a3a3a3;font-size:12px;">Autonomous Decision Engine · {timestamp}</p>
      </div>

      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        <tr>
          <td style="padding:10px;border:1px solid #262626;color:#a3a3a3;font-size:12px;width:40%;">DOMAIN</td>
          <td style="padding:10px;border:1px solid #262626;font-size:14px;font-weight:bold;">{domain_label}</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #262626;color:#a3a3a3;font-size:12px;">METRIC BREACHED</td>
          <td style="padding:10px;border:1px solid #262626;font-size:14px;">{metric.replace('_',' ').upper()}: <strong>{value:.2f}</strong> (threshold: {threshold})</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #262626;color:#a3a3a3;font-size:12px;">AUTONOMOUS ACTION</td>
          <td style="padding:10px;border:1px solid #262626;font-size:14px;font-weight:bold;color:{action_color};">{action.replace('_',' ')}</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #262626;color:#a3a3a3;font-size:12px;">RISK LEVEL</td>
          <td style="padding:10px;border:1px solid #262626;font-size:14px;font-weight:bold;color:{risk_color};">{risk_level}</td>
        </tr>
        <tr>
          <td style="padding:10px;border:1px solid #262626;color:#a3a3a3;font-size:12px;">EXPECTED DAILY LOSS</td>
          <td style="padding:10px;border:1px solid #262626;font-size:14px;color:#ef4444;font-weight:bold;">${expected_loss_usd:,.2f} / day</td>
        </tr>
      </table>

      <div style="margin-bottom:24px;">
        <h3 style="color:#a3a3a3;font-size:12px;margin-bottom:8px;">DRIFTED FEATURES</h3>
        {features_html}
      </div>

      <div style="border-top:1px solid #262626;padding-top:16px;">
        <p style="color:#525252;font-size:11px;margin:0;">
          This is an automated alert from <strong style="color:#ffffff;">Aether AI Enterprise Engine</strong>.<br/>
          Visit your dashboard to take action or approve/reject the recommendation.
        </p>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Aether AI] ⚡ {action} Alert — {domain_label} | Risk: {risk_level}"
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["recipient"]
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(cfg["sender"], cfg["password"])
            smtp.sendmail(cfg["sender"], cfg["recipient"], msg.as_string())
        return {"sent": True, "recipient": cfg["recipient"]}
    except smtplib.SMTPAuthenticationError:
        return {"sent": False, "reason": "Gmail SMTP auth failed. Check GMAIL_SENDER and GMAIL_APP_PASSWORD in .env"}
    except Exception as e:
        return {"sent": False, "reason": str(e)}


def check_and_fire_alerts(domain: str, metric: str, value: float, rules: list, decision: dict, drift: dict) -> list:
    """
    Scan active alert rules. If a threshold is breached, fire a real email.
    Returns list of fired alerts.
    """
    fired = []
    for rule in rules:
        if not rule.get("enabled"):
            continue
        if rule.get("domain") != domain and rule.get("domain") != "all":
            continue
        if rule.get("metric") != metric:
            continue
        if value > rule.get("threshold", 9999):
            if rule.get("channel") == "email":
                result = send_alert_email(
                    domain=domain,
                    metric=metric,
                    value=value,
                    threshold=rule["threshold"],
                    action=decision.get("action", "UNKNOWN"),
                    risk_level=decision.get("risk_level", "UNKNOWN"),
                    expected_loss_usd=decision.get("expected_daily_loss_usd", 0),
                    drift_features=drift.get("drifted_features", []),
                )
                fired.append({"rule_id": rule["id"], "channel": "email", "result": result})
    return fired
