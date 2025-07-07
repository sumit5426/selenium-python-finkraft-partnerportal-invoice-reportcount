from pymongo import MongoClient
from datetime import datetime, timedelta
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To
from sendgrid.helpers.mail import Personalization, Cc
import os
from dotenv import load_dotenv
import re


# Load environment variables from .env file
load_dotenv()
with open("run_id.txt", "r") as f:
    run_id = f.read().strip()

mongo_db_username = os.environ.get("MONGO_DB_USERNAME")
mongo_db_password = os.environ.get("MONGO_DB_PASSWORD")
api_key = os.environ.get("SENDGRID_API_KEY").strip()
template_id = os.environ.get("TEMPLATE_ID")

# Connect to MongoDB
connection_string = (f"mongodb://{mongo_db_username}:{mongo_db_password}"
                             "@mongodb.centralindia.cloudapp.azure.com/admin?"
                             "directConnection=true&serverSelectionTimeoutMS=5000&appName=mongosh+2.2.3")
client = MongoClient(connection_string)
db = client['gstservice']
collection_invoice = db["selenium-summary-report"]
collection_excel = db["selenium-summary-excel-report"]


# Ensure the API key and template ID are set
if not api_key or not template_id:
    raise ValueError("SENDGRID_API_KEY and TEMPLATE_ID must be set in the .env file.")



def get_invoice_summary_data_for_today():
    """
    Returns today's invoice summary data.
    """
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Looking for invoice summary data with invoice_initialization_date_time = {today_date}")
    data = list(collection_invoice.find(
        {"runId": run_id},
        {"_id": 0}
    ))
    if not data:
        print("No invoice summary data found for today.")
    return data

def get_excel_summary_data_for_today():
    """
    Returns today's excel summary data.
    """
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Looking for excel summary data with invoice_initialization_date_time = {today_date}")
    data = list(collection_excel.find(
        {"runId": run_id},
        {"_id": 0}
    ))
    if not data:
        print("No excel summary data found for today.")
    return data

def prepare_combined_table_data(invoice_data, excel_data):
    """
    Combines and formats data from both collections for the email template.
    """
    invoice_table_data = []
    excel_table_data = []


    # Add invoice data
    for item in invoice_data:
        remark = item.get("remark", "")
        test_status_count = item.get("TestStausAsPerInvCount", "")
        test_status_time = item.get("TestStausAsPerInvTime", "")
        row_class = "row-remark" if remark else ("row-fail" if test_status_count == "FAIL" or test_status_time == "FAIL" else "row-pass")
        invoice_table_data.append({
            "portalName": item.get("portalName", ""),
            "workspaceName": item.get("workspaceName", ""),
            "invoice_initialization_date_time": item.get("invoice_initialization_date_time", ""),
            "invoiceDownloadUIFlag": item.get("invoiceDownloadUIFlag", ""),
            "invoiceReceivedBackendFlag": item.get("invoiceReceivedBackendFlag", ""),
            "totalFilesInUI": item.get("totalFilesInUI", ""),
            "totalFilesInDB": item.get("totalFilesInDB", ""),
            "totalFilesInZip": item.get("totalFilesInZip", ""),
            "fileDifference": item.get("fileDifference", ""),
            "perInvoiceDownloadTimeBasedOnDB": item.get("perInvoiceDownloadTimeBasedOnDB", ""),
            "perInvoiceDownloadTimeBasedOnZip": item.get("perInvoiceDownloadTimeBasedOnZip", ""),
            "TestStatusAsPerInvCount": test_status_count,
            "TestStatusAsPerInvTime": test_status_time,
            "remark": remark,
            "row_class": row_class
        })

    # Add excel data
    for item in excel_data:
        remark = item.get("remark", "")
        test_status_row = item.get("testStatusWrtRow", "") # Note: Key change
        test_status_time = item.get("testStatusWrtTime", "") # Note: Key change
        row_class = "row-remark" if remark else ("row-fail" if test_status_row == "FAIL" or test_status_time == "FAIL" else "row-pass")
        excel_table_data.append({
            "portalName": item.get("portalName", ""),
            "workspaceName": item.get("workspaceName", ""),
            "report_initialization_date_time": item.get("report_initialization_date_time", ""),
            "reportDownloadUIFlag": item.get("reportDownloadUIFlag", ""),
            "reportReceivedBackendFlag": item.get("reportReceivedBackendFlag", ""),
            "totalColumnsInUI": item.get("totalColumnsInUI", ""),
            "totalRowsInUI": item.get("totalRowsInUI", ""),
            "totalRowsInDB": item.get("totalRowsInDB", ""),
            "totalRowsInExcel": item.get("totalRowsInExcel", ""),
            "totalColumnsInExcel": item.get("totalColumnsInExcel", ""),
            "RowsDifference": item.get("rowDifference", ""),
            "totalTime": item.get("totalTime", ""),
            "testStatusWrtTime": test_status_time,
            "testStatusWrtRow": test_status_row,
            "remark": remark,
            "row_class": row_class
        })

    return invoice_table_data, excel_table_data

def send_email(table_data):
    # Create dynamic template data
    invoice_data_list, excel_data_list = table_data

    dynamic_template_data = {
        "invoice_table_data": invoice_data_list,
        "excel_table_data": excel_data_list,
        "report_date": datetime.now().strftime("%Y-%m-%d")
    }

    # Create the SendGrid message
    from_email = Email("sushmitha@kgrp.in")

    mail = Mail()
    mail.from_email = from_email
    mail.template_id = template_id

    personalization = Personalization()
    to_emails = ["sumit@kgrp.in"]
    for email in to_emails:
        personalization.add_to(Email(email))
    cc_emails = ["sushmitha.sonu02@gmail.com"]
    for email in cc_emails:
        personalization.add_cc(Email(email))

    # personalization = Personalization()
    # to_emails = ["ambuj@finkraft.ai", "ranjith@kgrp.in"]
    # for email in to_emails:
    #     personalization.add_to(Email(email))
    # cc_emails = ["venu@kgrp.in", "tabrez@kgrp.in", "komalkant@kgrp.in", "kj@kgrp.in", "arnavjain@kgrp.in",
    #              "sumit@kgrp.in", "sushmitha.sonu02@gmail.com"]
    # for email in cc_emails:
    #     personalization.add_cc(Email(email))

    personalization.dynamic_template_data = dynamic_template_data

    mail.add_personalization(personalization)

    try:
        sg = sendgrid.SendGridAPIClient(api_key=api_key)
        response = sg.send(mail)
        print(f"Email sent: Status Code {response.status_code}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def trigger_sendgrid_email():
    invoice_data = get_invoice_summary_data_for_today()
    excel_data = get_excel_summary_data_for_today()

    # Confirm data type
    if (isinstance(invoice_data, list) and invoice_data) or (isinstance(excel_data, list) and excel_data):
        invoice_table_data, excel_table_data = prepare_combined_table_data(invoice_data, excel_data) # Get two lists
        # Send email if either list has data
        if invoice_table_data or excel_table_data:
             # Pass both lists as a tuple to send_email
             send_email((invoice_table_data, excel_table_data))
        else:
            print("No data to send in email.") # Should be caught by the outer if, but good safeguard
    else:
        print("No data found for today from either collection to send in email.")



if __name__ == "__main__":
    trigger_sendgrid_email()
