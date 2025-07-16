# insert_mongo.py
import json
import os
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv
from pymongo import MongoClient

# ────────────────────────────────────────────────────────────────
#  Load credentials from .env
# ────────────────────────────────────────────────────────────────
load_dotenv()                                            # looks for .env in cwd

MONGO_DB_USERNAME = os.getenv("MONGO_DB_USERNAME", "")
MONGO_DB_PASSWORD = os.getenv("MONGO_DB_PASSWORD", "")
MONGO_HOST        = os.getenv("MONGO_HOST", "mongodb.centralindia.cloudapp.azure.com")
MONGO_PORT        = os.getenv("MONGO_PORT", "27017")     # ← use digits only
MONGO_DB          = "gstservice"                        # logical database
MONGO_COLLECTION  = "selenium_creds_summary"

# Escape user & password per RFC‑3986
quoted_user = quote_plus(MONGO_DB_USERNAME)
quoted_pw   = quote_plus(MONGO_DB_PASSWORD)

# Build the final Mongo connection string
MONGO_URI = (
    f"mongodb://{quoted_user}:{quoted_pw}@{MONGO_HOST}:{MONGO_PORT}/admin?"
    "directConnection=true&serverSelectionTimeoutMS=5000&appName=gst‑run"
)

# ────────────────────────────────────────────────────────────────
#  I/O helpers
# ────────────────────────────────────────────────────────────────
def insert_into_mongo(payload: dict) -> None:
    """
    Insert the summary payload into MongoDB.
    Gracefully degrades (prints a warning) if connection fails.
    """
    try:
        client = MongoClient(MONGO_URI)
        client[MONGO_DB][MONGO_COLLECTION].insert_one(payload)
        print("✅  Inserted summary into MongoDB")
    except Exception as e:
        print(f"❌  Mongo insert failed: {e}")


def write_json_summary(payload: dict, filename: str = "summary.json") -> None:
    """
    Always dump a local JSON file, even if Mongo insertion fails.
    """
    try:
        with open(filename, "w", encoding="utf‑8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"✅  Summary saved to {filename}")
    except Exception as e:
        print(f"❌  Failed to write JSON summary: {e}")


def prepare_report(
    portal: str,
    workspace: str,
    creds_type: str,
    ag_pg_results: list[tuple[str, str, str]],
    edit_result: bool,
) -> dict:
    """
    Assemble the final report structure expected by downstream tools.
    `ag_pg_results` = [(gstin, ag_status, expected_status), …]
    """
    summary: dict = {
        "portal": portal,
        "workspace": workspace,
        "creds_type": creds_type,
        "bulk_upload_success": True,     # hard‑coded; flip outside if needed
        "edit_success": edit_result,
        "status": True,                  # becomes False if any mismatch
        "remarks": [],
        "timestamp": datetime.utcnow() 
    }

    # Flag mismatches
    for gstin, ag_stat, expected_stat in ag_pg_results:
        if ag_stat != expected_stat:
            summary["status"] = False
            summary["remarks"].append(
                f"{gstin}: AG='{ag_stat}' ≠ PG='{expected_stat}'"
            )

    return summary
