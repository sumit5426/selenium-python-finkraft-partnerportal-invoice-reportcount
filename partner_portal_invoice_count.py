import json
import time
import os
import uuid
import zipfile
import shutil
import glob
import tempfile
import psycopg2
from psycopg2 import sql
from pymongo import MongoClient
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.support.wait import WebDriverWait
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
run_id = datetime.now().strftime('%Y%m%d%H%M%S')
with open("run_id.txt", "w") as f:
    f.write(run_id)

morning_workspaces =[
    {
      "uri": "https://cleartrip.finkraft.ai/auth/signin",
      "workspace_name": "Unitus capital",
      "table_name": "flight_recon_main",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "Unitus capital"
  },

{    "uri": "https://balmer.finkraft.ai/auth/signin",
      "workspace_name": "Enforcement directorate",
      "table_name": "airline_recon_balmer",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "ENFORCEMENT DIRECTORATE"
  },
  {
    "uri": "https://myyatra.finkraft.ai/auth/signin",
    "workspace_name": "Minda industries limited yatra",
    "table_name": "flight_recon_yatra",
    "status_column_name": "StatusofInvoice",
    "status_column_value": "Invoice Received",
    "db_workspace_name": "MINDA INDUSTRIES LIMITED Yatra"
  },
  {
    "uri": "https://mmt.finkraft.ai/auth/signin",
    "workspace_name": "Mankind pharma",
    "table_name": "airline_recon_mmt",
    "status_column_name": "MainInvoiceStatus",
    "status_column_value": "Invoice Received",
    "db_workspace_name": "MANKIND PHARMA LIMITED"
  },
   {
      "uri": "https://pyt.finkraft.ai/auth/signin",
      "workspace_name": "Om sai intex",
      "table_name": "airline_recon_py",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "Om Sai Intex"
  },
  {
      "uri": "https://fcm.finkraft.ai/auth/signin",
      "workspace_name": "Infifresh",
      "table_name": "airline_recon_fcm",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "INFIFRESH"
 },
 {
      "uri": "https://bcd.finkraft.ai/auth/signin",
      "workspace_name": "Cp kelco",
      "table_name": "airline_recon_bcd",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "CP Kelco"
 },
{
        "uri": "https://atpi.finkraft.ai/auth/signin",
        "workspace_name": "British international investment",
        "table_name": "airline_recon_atpi",
        "status_column_name": "InvoiceStatus",
        "status_column_value": "Invoice Received",
        "db_workspace_name": "British International Investment"
}
]
afternoon_workspaces =[
    {
      "uri": "https://cleartrip.finkraft.ai/auth/signin",
      "workspace_name": "Saksoft",
      "table_name": "flight_recon_main",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "Saksoft"
  },

{    "uri": "https://balmer.finkraft.ai/auth/signin",
      "workspace_name": "Eastern regional office aicte kolkata",
      "table_name": "airline_recon_balmer",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "EASTERN REGIONAL OFFICE AICTE KOLKATA"
  },
  {
    "uri": "https://myyatra.finkraft.ai/auth/signin",
    "workspace_name": "Herbalife international india p ltd yatra",
    "table_name": "flight_recon_yatra",
    "status_column_name": "StatusofInvoice",
    "status_column_value": "Invoice Received",
    "db_workspace_name": "HERBALIFE INTERNATIONAL INDIA P LTD Yatra"
  },
  {
    "uri": "https://mmt.finkraft.ai/auth/signin",
    "workspace_name": "Kotak securities",
    "table_name": "airline_recon_mmt",
    "status_column_name": "MainInvoiceStatus",
    "status_column_value": "Invoice Received",
    "db_workspace_name": "Kotak Securities"
  },
   {
      "uri": "https://pyt.finkraft.ai/auth/signin",
      "workspace_name": "Blue heaven cosmetics",
      "table_name": "airline_recon_py",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "BLUE HEAVEN COSMETICS"
  },
  {
      "uri": "https://fcm.finkraft.ai/auth/signin",
      "workspace_name": "One ocean network",
      "table_name": "airline_recon_fcm",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "ONE OCEAN NETWORK"
 },
 {
      "uri": "https://bcd.finkraft.ai/auth/signin",
      "workspace_name": "Viewics",
      "table_name": "airline_recon_bcd",
      "status_column_name": "InvoiceStatus",
      "status_column_value": "Invoice Received",
      "db_workspace_name": "Viewics"
 },
{
        "uri": "https://atpi.finkraft.ai/auth/signin",
        "workspace_name": "The great eastern shipping",
        "table_name": "airline_recon_atpi",
        "status_column_name": "InvoiceStatus",
        "status_column_value": "Invoice Received",
        "db_workspace_name": "The Great Eastern Shipping"
}
]

run_set = os.environ.get("RUN_SET", "morning")
if run_set == "morning":
    portals = morning_workspaces
else:
    portals = afternoon_workspaces


login_username = os.environ.get("LOGIN_USERNAME")
login_password = os.environ.get("LOGIN_PASSWORD")
mongo_db_username = os.environ.get("MONGO_DB_USERNAME")
mongo_db_password = os.environ.get("MONGO_DB_PASSWORD")
pg_db_username = os.environ.get("PG_DB_USERNAME")
pg_db_password = os.environ.get("PG_DB_PASSWORD")



email_id = login_username
password = login_password

def initialize_driver(download_dir):
    print("Initializing the Chrome driver...")
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless=new")  # Use "new" headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    })

    seleniumwire_options = {'verify_ssl': False}
    driver = webdriver.Chrome(options=chrome_options, seleniumwire_options=seleniumwire_options)
    driver.implicitly_wait(7)
    return driver

def login_and_select_workspace(driver, uri, workspace_name):
    wait = WebDriverWait(driver, 10)
    driver.get(uri)
    page_title = driver.title
    print(page_title)
    partner_portal_name = page_title.split("-")[0].strip()
    EMAIL_TEXTBOX = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Email']")))
    EMAIL_TEXTBOX.send_keys(email_id)
    SUBMIT_BUTTON = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@type="submit"]')))
    SUBMIT_BUTTON.click()
    PASSWORD_TEXTBOX = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Password']")))
    PASSWORD_TEXTBOX.send_keys(password)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"]'))).click()
    print("Successfully logged in...")
    time.sleep(5)
    max_attempts = 4
    for attempt in range(max_attempts):
        try:
            workspace_dropdown = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'ant-dropdown-trigger')]")))
            workspace_dropdown.click()
            workspace_element = wait.until(
                EC.element_to_be_clickable((By.XPATH, f"//p[normalize-space()='{workspace_name}']")))
            try:
                workspace_element.click()
            except ElementClickInterceptedException:
                print("Element not clickable directly. Scrolling to it...")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", workspace_element)
                time.sleep(1)  # Wait for scroll to complete
                workspace_element.click()
            time.sleep(1)
            menu_item = wait.until(EC.element_to_be_clickable((By.XPATH, '(//div[@class="MenuItem "])[2]')))
            menu_item.click()
            bulk_download = wait.until(EC.element_to_be_clickable((By.XPATH, '(//div[@class="BulkDownload"])[1]')))
            bulk_download.click()
            try:
                download_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[text()="Initiate Download"]'))
                )
                download_button.click()
                ui_alert_shown_flag = True
                print("Alert shown")
            except Exception as e:
                ui_alert_shown_flag = False
                print("Alert not shown")
            return ui_alert_shown_flag, partner_portal_name
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_attempts - 1:
                print("Retrying workspace selection...")
                driver.refresh()
                time.sleep(5)
            else:
                print("Max attempts reached. Raising the error.")
                return False, partner_portal_name
    return False, partner_portal_name

def capture_report_message_and_id(driver):
    print("📡 Monitoring network requests to capture the invoice report API response...")
    timeout = time.time() + 60  # 60 seconds timeout
    driver.requests.clear()
    report_id = None
    already_generated = False
    found_url = None
    while time.time() < timeout:
        matching_requests = [
            req for req in driver.requests
            if req.response
               and '/report/invoicedownload' in req.url
               and 'application/json' in req.response.headers.get('Content-Type', '')
        ]
        for request in matching_requests:
            try:
                response_body = request.response.body.decode('utf-8', errors='ignore')
                body_data = json.loads(response_body)
                message = body_data.get('message', '')
                if message == "Invoice request submitted successfully. Will send you the invoice once ready":
                    if 'data' in body_data and 'reportId' in body_data['data']:
                        report_id = body_data['data']['reportId']
                        print(f"ReportID Extracted successfully from Network tab: {report_id}")
                        found_url = request.url
                        break
                elif message == "This invoices has already been generated. We have sent you the link in your email.":
                    print("Invoice already generated for this workspace today. Skipping to next workspace.")
                    already_generated = True
                    break
                else:
                    print(f"Received unexpected message: {message}")
            except Exception as e:
                print(f"⚠ Error parsing JSON from {request.url}: {e}")
        if report_id or already_generated:
            break
        time.sleep(1)
    if already_generated:
        return "ALREADY_GENERATED"
    if not report_id:
        print("❌ reportId not found in network traffic within timeout.")
        return None
    return report_id


def get_count_from_postgres(connection_params, table_name, status_column, status_value, workspace_name):
    """
    Connects to PostgreSQL and returns the count of rows filtered by status and workspace.
    """
    max_retries = 3
    retry_delay = 2  # seconds
    conn = None
    cursor = None
    result = None

    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=connection_params['host'],
                port=connection_params['port'],
                database=connection_params['database'],
                user=connection_params['user'],
                password=connection_params['password']
            )
            cursor = conn.cursor()

            query = sql.SQL("""
                SELECT COUNT(*)
                FROM {table}
                WHERE {status_col} = %s
                  AND "Workspace" = %s
            """).format(
                table=sql.Identifier(table_name),
                status_col=sql.Identifier(status_column)
            )

            cursor.execute(query, (status_value, workspace_name))
            result = cursor.fetchone()[0]

            cursor.close()
            conn.close()
            print(f" - 📄 Total PDF invoices present in the UI is: {result}")
            return result

        except Exception as e:
            print(f"Error querying PostgreSQL (Attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("Max retries reached. Could not connect to PostgreSQL.")
                result = None
        finally:
            try:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
            except Exception as e:
                print(f"Error closing PostgreSQL connection: {e}")
                return result
    return result


def remarks_to_mongo_db(partner_portal_name,workspace_name,db,current_timestamp,errormessage):
    error_collection = db["selenium-summary-report"]
    data_to_insert = {
        "invoice_initialization_date_time": current_timestamp,
        "portalName":partner_portal_name,
        "workspaceName":workspace_name,
        "remark": errormessage,
        "invoiceDownloadUIFlag": "--",
        "invoiceReceivedBackendFlag": "--",
        "totalFilesInUI":"--",
        "totalFilesInDB": "--",
        "totalFilesInZip": "--",
        "fileDifference": "--",
        "perInvoiceDownloadTimeBasedOnDB": "--",
        "perInvoiceDownloadTimeBasedOnZip": "--",
        "TestStausAsPerInvCount": "--",
        "TestStausAsPerInvTime": "--",
        "runId":run_id
    }
    error_collection.insert_one(data_to_insert)

def wait_for_report_completion(db, report_id,partner_portal_name,workspace_name,ui_invoice_count):
    collection = db['invoice_report']
    print(f"🔎 Searching in MongoDB for reportId: {report_id}...")
    doc = collection.find_one({"reportId": report_id})
    if not doc:
        current_timestamp = datetime.now().strftime('%Y-%m-%d')
        formatted_created_at_time = datetime.fromtimestamp(current_timestamp).strftime('%Y-%m-%d')
        remarks_to_mongo_db(partner_portal_name, workspace_name, db, current_timestamp,
                            "Document with reportId not found in MongoDB.")
        print("Document with reportId not found in MongoDB.")
        return None
    created_at = doc["createdAt"] / 1000  # Convert from milliseconds to seconds
    formatted_created_at_time = datetime.fromtimestamp(created_at).strftime('%d-%b-%Y %I:%M %p')
    print("🕒 Created At:", formatted_created_at_time)
    timeout=(ui_invoice_count*10)
    print(f"timeout period for {partner_portal_name} is {timeout} sec")
    poll_interval = 10
    start_time = time.time()
    while time.time() - start_time < timeout:
        doc = collection.find_one({"reportId": report_id})
        if doc and doc["status"] == "COMPLETED":
            completed_time = time.time()
            print("Status changed to COMPLETED at", time.ctime(completed_time))
            total_time = int(completed_time - created_at)
            print(f"Total time taken: {total_time} seconds")
            total_files = doc.get("totalfiles")
            if total_files is None:
                print("⚠️ 'totalFiles' field not found in MongoDB document.")
                total_files = 0
            else:
                print(f"🗃️ Total number of invoice PDFs to be downloaded as per DB: {total_files}")
            file_hash = doc.get("filehash")
            return {
                "total_files": total_files,
                "file_hash": file_hash,
                "total_time": total_time,
                "formatted_created_at_time": formatted_created_at_time
            }
        print("⌛ Still PENDING... checking again in 10 seconds")
        time.sleep(poll_interval)

    print("Timeout: Report did not complete in estimated minutes.")
    remarks_to_mongo_db(partner_portal_name,workspace_name,db,formatted_created_at_time,"Report did not complete in estimated minutes.")
    print("❌Error Report inserted successfully into DB")
    return None


def download_and_verify_invoices(driver, file_hash, total_files, total_time, formatted_created_at_time, partner_portal_name, workspace_name, ui_alert_shown_flag, db,download_dir,ui_invoice_count):
    if not file_hash:
        print("❌ fileHash not found in MongoDB.")
        return False, "fileHash not found in MongoDB."
    file_hash_flag = True
    print("✅ fileHash is present. Flag:", file_hash_flag)
    download_url = f"https://files.finkraft.ai/invoice-{file_hash}"
    print(f"🌐 Navigating to file download URL")
    driver.get(download_url)
    time.sleep(3)
    try:
        download_btn_1 = driver.find_element(By.XPATH, "//a[@id='downloadLink']")
        download_btn_1.click()
        time.sleep(3)
        download_btn_2 = driver.find_element(By.XPATH, "//a[@id='downloadLink']")
        download_btn_2.click()
        print("⬇️ Invoice download links clicked successfully.")
    except Exception as e:
        print(f"❌ Error clicking download buttons: {e}")
        return False, f"Error clicking download buttons: {str(e)}"
    timeout = time.time() + 70  # wait up to 70 seconds
    zip_file_path = None
    print("⏳ Waiting for zip file to appear in Downloads...")
    while time.time() < timeout:
        zip_files = glob.glob(os.path.join(download_dir, "*.zip"))
        if zip_files:
            zip_file_path = max(zip_files, key=os.path.getctime)  # get latest zip
            print(f"✅ Found zip file: {zip_file_path}")
            break
        time.sleep(2)
    if not zip_file_path:
        print("❌ Zip file not downloaded.")
        return False, "Zip file not downloaded."
    unique_folder_name = f"invoices_extracted_{uuid.uuid4()}"
    extract_path = os.path.join(download_dir, unique_folder_name)
    os.makedirs(extract_path, exist_ok=True)
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        zip_ref.extractall(extract_path)
    print(f"📂 Extracted zip to: {extract_path}")

    pdf_files = glob.glob(os.path.join(extract_path, "**/*.pdf"), recursive=True)
    downloaded_file_count = len(pdf_files)
    print(f"📄 PDF invoices found: {downloaded_file_count}")

    try:
        os.remove(zip_file_path)
        shutil.rmtree(extract_path)
        print("🧹 Cleaned up zip and extracted folder.")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

    print("🧮 Verifying invoice download count consistency...")
    print(f" - 📦 Total invoices reported in MongoDB:  {total_files}")
    print(f" - 📄 Total PDF invoices extracted from the downloaded zip: {downloaded_file_count}")

    if downloaded_file_count == 0:
        print("❌ No PDF files downloaded. Cannot calculate per-invoice time.")
        return False, "No PDF files downloaded. Cannot calculate per-invoice time."
    actual_time_per_invoice = total_time / downloaded_file_count
    testStatusAsPerFile = "PASS" if actual_time_per_invoice <= 2 else "FAIL"
    actual_time_per_invoice_db = total_time / total_files
    testStatusAsPerDB = "PASS" if actual_time_per_invoice_db <= 2 else "FAIL"
    time_per_invoice = total_time / total_files if total_files else 0
    print(f"⏱️ Time taken *per invoice* based on actual downloads: {actual_time_per_invoice:.2f} seconds")
    print(f"⏱️ Time taken *per invoice* based on DB report: {time_per_invoice:.2f} seconds")
    time_diff = actual_time_per_invoice - time_per_invoice
    print("Time difference between downloads" , time_diff)
    status_time_diff = "PASS" if actual_time_per_invoice <= 2 else "FAIL"
    print("Flag result Time taken *per invoice* based on actual downloads ", status_time_diff)
    formatted_time_perinvoicetime_Zip = float(f"{actual_time_per_invoice:.2f}")
    formatted_time_perinvoicetime_DB = float(f"{time_per_invoice:.2f}")
    print(f"📊 Difference in time per invoice (Actual - Reported): {time_diff:.2f} seconds")
    invoice_diff = total_files - downloaded_file_count
    print("Invoice difference between DB and Folder", invoice_diff)
    status_invoice_diff = "PASS" if invoice_diff == 0 else "FAIL"
    print("Per invoice time difference between DB and Folder", status_invoice_diff)

    summary_collection = db["selenium-summary-report"]
    data_to_insert = {
        "portalName": partner_portal_name,
        "workspaceName": workspace_name,
        "invoice_initialization_date_time": formatted_created_at_time,
        "invoiceDownloadUIFlag": ui_alert_shown_flag,
        "invoiceReceivedBackendFlag": file_hash_flag,
        "totalFilesInUI":ui_invoice_count,
        "totalFilesInDB": total_files,
        "totalFilesInZip": downloaded_file_count,
        "fileDifference": invoice_diff,
        "perInvoiceDownloadTimeBasedOnDB": formatted_time_perinvoicetime_DB,
        "perInvoiceDownloadTimeBasedOnZip": formatted_time_perinvoicetime_Zip,
        "TestStausAsPerInvCount": status_invoice_diff,
        "TestStausAsPerInvTime": status_time_diff,
        "remark" : "",
        "runId": run_id
    }
    summary_collection.insert_one(data_to_insert)
    print("✅ Report inserted successfully into DB")

    if invoice_diff == 0:
        print("🟩 Invoice count matches exactly between DB and downloaded folder.")
    elif invoice_diff > 0:
        print(f"🟨 {invoice_diff} invoice(s) reported in DB but missing in folder.")
    else:
        print(f"🟥 {abs(invoice_diff)} extra invoice(s) found in folder not reported in DB.")

    if actual_time_per_invoice > 2:
        print("❌ Test Failed: More than 2 seconds per invoice")
    else:
        print("✅ Test Passed: Invoice download time is within limits")
    return True, ""


def main():

    for portal in portals:
        retry_count = 0
        max_retries = 1  # Only retry once
        while retry_count <= max_retries:
            connection_string = (f"mongodb://{mongo_db_username}:{mongo_db_password}"
                                 "@mongodb.internal.finkraftai.com/admin?"
                                 "directConnection=true&serverSelectionTimeoutMS=20000&appName=mongosh+2.2.3")
            client = MongoClient(connection_string)
            db = client['gstservice']
            print(f"Starting automation for portal:{portal['uri']} and workspace:{portal['workspace_name']}")
            download_dir = tempfile.mkdtemp(prefix="downloads_")
            driver = initialize_driver(download_dir)
            try:
                ui_alert_shown_flag, partner_portal_name = login_and_select_workspace(
                    driver,
                    portal["uri"],
                    portal["workspace_name"]
                )

                if not ui_alert_shown_flag:
                    print("Workspace selection failed after all retries. Moving to next portal.")
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    remarks_to_mongo_db(partner_portal_name, portal['workspace_name'], db, current_timestamp,
                                        "Workspace selection failed after two times retry attempts")
                    break

                report_id = capture_report_message_and_id(driver)
                if report_id == "ALREADY_GENERATED":
                    print(f"Workspace  {portal['workspace_name']} already has a report for today, skipping.")
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    remarks_to_mongo_db(partner_portal_name, portal['workspace_name'], db, current_timestamp,
                                        " already has a report for today, skipping.")
                    break
                if report_id is None:
                    # Log error to MongoDB and skip to next portal if report_id is not found
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    print("Skipping further processing for this portal due to missing Report ID.")
                    if retry_count == 0:
                        retry_count += 1
                        continue
                    remarks_to_mongo_db(partner_portal_name, portal['workspace_name'], db, current_timestamp,
                                        " Report ID not captured.")
                    break

                pg_connection_params = {
                    "host": "postgres.centralindia.cloudapp.azure.com",
                    "port": 5432,
                    "database": "airlines_db",
                    "user": pg_db_username,
                    "password": pg_db_password
                }
                table_name = portal['table_name']
                status_column = portal['status_column_name']
                status_value = portal['status_column_value']
                workspace_name = portal['db_workspace_name']

                ui_invoice_count = get_count_from_postgres(
                    pg_connection_params,
                    table_name,
                    status_column,
                    status_value,
                    workspace_name
                )

                if ui_invoice_count is None:
                    print("❌ Failed to get invoice count from PostgreSQL. Skipping further processing.")
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    remarks_to_mongo_db(partner_portal_name, portal['workspace_name'], db, current_timestamp,
                                        "Failed to get invoice count from PostgreSQL")
                    break

                report_info = wait_for_report_completion(db, report_id, partner_portal_name,
                                                         portal["workspace_name"], ui_invoice_count)

                if report_info is None:
                    break
                download_success,error_message = download_and_verify_invoices(
                    driver,
                    report_info["file_hash"],
                    report_info["total_files"],
                    report_info["total_time"],
                    report_info["formatted_created_at_time"],
                    partner_portal_name,
                    portal['workspace_name'],
                    ui_alert_shown_flag,
                    db, download_dir, ui_invoice_count
                )
                if download_success is False:
                    if retry_count == 0:
                        retry_count += 1
                        continue
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    remarks_to_mongo_db(partner_portal_name, portal['workspace_name'], db, current_timestamp,
                                        error_message)
                    break

            except Exception as e:
                print(f"⚠️ Error processing portal {portal['uri']}: {e}")
                try:
                    current_timestamp = datetime.now().strftime('%Y-%m-%d')
                    # formatted_created_at_time = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                    subdomain = portal['uri'].split('//')[-1].split('/')[0].replace('.finkraft.ai', '')
                    max_length = 50
                    short_exception = str(e)[:max_length] + ("..." if len(str(e)) > max_length else "")
                    remarks_to_mongo_db(subdomain, portal['workspace_name'], db, current_timestamp,
                                        f" Exception during processing: {short_exception}")
                except Exception as log_e:
                    print(f"❌ Error while attempting to log exception to MongoDB: {log_e}")
            finally:
                if driver:
                    driver.quit()

            print(f"Completed automation for portal: {portal['uri']}\n\n")
            break

if __name__ == "__main__":
    main()
