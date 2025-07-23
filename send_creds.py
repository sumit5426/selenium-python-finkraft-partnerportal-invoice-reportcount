import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, Personalization

# Load environment variables
load_dotenv()

# MongoDB setup
MONGO_USER = os.getenv("MONGO_DB_USERNAME")
MONGO_PASS = os.getenv("MONGO_DB_PASSWORD")
MONGO_URI = (
    f"mongodb://{MONGO_USER}:{MONGO_PASS}"
    "@mongodb.centralindia.cloudapp.azure.com/admin?directConnection=true&serverSelectionTimeoutMS=5000"
)
client = MongoClient(MONGO_URI)
db = client["gstservice"]
gst_coll = db["selenium_creds_summary"]

# SendGrid setup
SG_API_KEY = os.getenv("SENDGRID_API_KEY")
TEMPLATE_ID = os.getenv("TEMPLATE_ID")
FROM_EMAIL = "sushmitha@kgrp.in"
TO_EMAILS = ["sushu.sushmitha02@gmail.com"]
# CC_EMAILS = ["sumit@kgrp.in"]

def fetch_today_gst_docs():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    docs = list(gst_coll.find({"timestamp": {"$regex": f"^{today}"}}, {"_id": 0}))
    print("Docs to send:", docs)
    return docs

def build_table_rows(docs):
    rows = []
    for d in docs:
        def safe(val): return str(val) if val is not None else "—"
        values = [
            "PASS" if d.get("bulk_upload_csv") else "FAIL",
            "PASS" if d.get("verifier_updated_pg") else "FAIL",
            "PASS" if d.get("verifier_to_pg_time_ok") else "FAIL",
            "PASS" if d.get("ag_updated_pg_status") else "FAIL",
            "PASS" if d.get("ag_update_time_ok") else "FAIL",
            "PASS" if d.get("cell_edit_success") else "FAIL",
            "PASS" if d.get("post_edit_pg_ag_sync") else "FAIL",
            "PASS" if d.get("post_edit_pg_ag_time_ok") else "FAIL",
        ]
        row_class = "row-fail" if "FAIL" in values else "row-pass"
        rows.append({
            "portal": safe(d.get("portal")),
            "workspace": safe(d.get("workspace")),
            "creds_type": safe(d.get("creds_type")),
            "bulk_upload_csv": values[0],
            "verifier_updated_pg": values[1],
            "verifier_to_pg_time_ok": values[2],
            "ag_updated_pg_status": values[3],
            "ag_update_time_ok": values[4],
            "cell_edit_success": values[5],
            "post_edit_pg_ag_sync": values[6],
            "post_edit_pg_ag_time_ok": values[7],
            "remarks": "; ".join([safe(r) for r in d.get("remarks", [])]) if d.get("remarks") else "—",
            "row_class": row_class,
        })
    return rows

def send_email(table_rows):
    if not SG_API_KEY or not TEMPLATE_ID:
        raise RuntimeError("SendGrid API key / template ID missing in .env")
    mail = Mail(from_email=FROM_EMAIL, to_emails=TO_EMAILS)
    print("Mail ", mail)
    mail.template_id = TEMPLATE_ID
    print("Template id ", TEMPLATE_ID)
    personalization = Personalization()
    for email in TO_EMAILS:
        personalization.add_to(Email(email))
    # for email in CC_EMAILS:
    #     personalization.add_cc(Email(email))
    personalization.dynamic_template_data = {"gst_table": table_rows}
    mail.add_personalization(personalization)
    try:
        api_key = os.getenv("SENDGRID_API_KEY")
        print(f"SENDGRID_API_KEY: {api_key}")
        sg = SendGridAPIClient(api_key)
        response = sg.send(mail)
        print(f"SendGrid response: {response.status_code}")
        print("SendGrid error body:")
        print(response.body.decode() if hasattr(response.body, 'decode') else response.body)
        print("Payload to SendGrid:")
        print(json.dumps({"gst_table": table_rows}, indent=2))
    except Exception as e:
        print(f"SendGrid send failed: {e}")

def trigger_creds():
    docs = fetch_today_gst_docs()
    if not docs:
        print("No GST‑creds summary docs for today → no e‑mail sent.")
        return
    rows = build_table_rows(docs)
    send_email(rows)

if __name__ == "__main__":
    trigger_creds()



# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail
# import os
# from dotenv import load_dotenv
# load_dotenv()

# message = Mail(
#         from_email='sushmitha@kgrp.in',  # must be verified in SendGrid
#         to_emails='sushmitha.sonu02@gmail.com',
#         subject='Test Subject',
#         html_content='<strong>Hello from SendGrid</strong>'
#     )
    

# api_key = os.getenv("SENDGRID_API_KEY")
# print(f"SENDGRID_API_KEY: {api_key}")
# sg = SendGridAPIClient(api_key)
# response = sg.send(message)

# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail
# import os
# from dotenv import load_dotenv
# load_dotenv()

# message = Mail(
#         from_email='sushmitha@kgrp.in',  # must be verified in SendGrid
#         to_emails='sushu.sushmitha02@gmail.com',
#         subject='Test Subject',
#     html_content=f"""
#         <p><strong>Workspace:</strong> Test123</p>
#         <p><strong>Creds Type:</strong> GST</p>
#         <p><strong>Remarks:</strong></p>
#         <ul>
#             <li>❌ [PG Pending Timeout] for 12WUTYH1234P1ZC</li>
#             <li>❌ [PG Pending Timeout] for 19TGYHU1234Y1ZY</li>
#             <li>❌ [Verifier → PG] PG not updated for some GSTINs.</li>
#         </ul>
#     """
# )
# try:
#     api_key = os.getenv("SENDGRID_API_KEY")
#     print(f"SENDGRID_API_KEY: {api_key}")
#     sg = SendGridAPIClient(api_key)
#     response = sg.send(message)
#     print(response.status_code)
# except Exception as e:
#     print(f"SendGrid send failed: {e}")
