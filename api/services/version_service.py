import os
import json
from datetime import datetime

VERSION_FILE = "models/model_versions.json"
def load_versions():
    if not os.path.exists(VERSION_FILE):
        return []
    with open(VERSION_FILE, "r") as f:
        return json.load(f)

def save_version(version, accuracy, latency, status):
    os.makedirs("models", exist_ok=True)
    versions = load_versions()
    new_entry = {
        "version": version,
        "accuracy": accuracy,
        "latency": latency,
        "status": status,
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
    versions.append(new_entry)
    with open(VERSION_FILE, "w") as f:
        json.dump(versions, f, indent=4)

def get_versions():
    return load_versions()