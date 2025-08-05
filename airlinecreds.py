import os
import time
from datetime import datetime, timezone
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, StaleElementReferenceException
from psycopg2 import sql
from insert_mongo import insert_into_mongo, prepare_report, write_json_summary,update_summary
from utils import resolve_expected_ag
import json
from send_creds import trigger_creds

now_utc = datetime.now(timezone.utc)
print(now_utc.isoformat())
# ------------------- 1.  CONFIGURATION --------------------------#
load_dotenv()

PORTAL_URL       = "https://myyatra.finkraft.ai/auth/signin"
WORKSPACE_NAME   = "Test123"
CSV_PATH         = "airlinecreds.csv"

PG_HOST          = "postgres.centralindia.cloudapp.azure.com"
PG_PORT          = 5432
PG_DATABASE      = "gstservice_db"
PG_USER          = os.getenv("PG_DB_USERNAME")
PG_PASSWORD      = os.getenv("PG_DB_PASSWORD")

LOGIN_USERNAME   = os.getenv("LOGIN_USERNAME")
LOGIN_PASSWORD   = os.getenv("LOGIN_PASSWORD")

X_CREDENTIALS_TAB  = "//div[contains(@class,'MenuItem')]//p[normalize-space()='Credentials']"
X_AIRLINE_TAB = "//div[@role='tab' and contains(@class, 'ant-tabs-tab-btn') and normalize-space()='Airline']"
X_BULK_UPLOAD_BUTTON = "//button[@id='bulkUpdateBtn' and span[text()='Bulk Upload']]"
X_SUBMIT = "//button[contains(@class,'ant-btn') and .//span[text()='Submit']]"
X_FILE_INPUT = "//input[@type='file']"
X_SEARCH_PAN = "//input[@placeholder='Search Airline, Username or PAN']" # Use the provided xpath



# ------------------------- DRIVER + DB ----------------------------
def init_driver() -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=opts, seleniumwire_options={"verify_ssl": False})
    driver.implicitly_wait(7)
    return driver

def pg_connect():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
        connect_timeout=10
    )

# ------------------------- LOGIN FLOW -----------------------------
class WorkspaceSwitchError(Exception):
    pass

def login_and_pick_workspace(driver):
    wait = WebDriverWait(driver, 15)
    driver.get(PORTAL_URL)
    page_title = driver.title
    print(page_title)
    partner_portal_name = page_title.split("-")[0].strip()
    print("Portal name:" , partner_portal_name)
    try : 
        wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Email']"))).send_keys(LOGIN_USERNAME)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))).click()
        wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Password']"))).send_keys(LOGIN_PASSWORD)
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()
        for attempt in range(3):
            try:
                wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'ant-dropdown-trigger')]"))).click()
                ws_el = wait.until(EC.element_to_be_clickable((By.XPATH, f"//p[normalize-space()='{WORKSPACE_NAME}']")))
                try:
                    ws_el.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ws_el)
                    ws_el.click()
                return
            except Exception:
                if attempt < 2:
                    driver.refresh()
                else:
                    raise RuntimeError("Could not choose workspace") 
        return partner_portal_name  
    except Exception as e: 
        print(f"Login failed: {e}")
        raise RuntimeError("Login failed, check your credentials or network connection.")

def upload_csv(driver, csv_path):
    try:
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
        print("Navigated to Credentials tab.")
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH , X_AIRLINE_TAB))).click()
        print("Navigated to Airline tab.")
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH , X_BULK_UPLOAD_BUTTON))).click()
        print("clicked on Bulk Upload button.")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, X_FILE_INPUT))).send_keys(os.path.abspath(csv_path))
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SUBMIT))).click()
        time.sleep(2)
        print("CSV uploaded successfully.")
    except ElementClickInterceptedException as e:
        print("Element was not clickable:", e)
    except Exception as e:
        # Handle any other exceptions that may occur
        if "file" in str(e).lower():
            print("File input element not found or not interactable.")
        elif "submit" in str(e).lower():
            print("Submit button element not found or not interactable.")
        else:
            print(f"Error uploading CSV :{e}")   

def refresh_grid(driver):    
    driver.refresh()
    WebDriverWait(driver , 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))) .click()
    WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.XPATH, X_AIRLINE_TAB))).click()
    print("Refreshing the grid to see the updated data.")
    time.sleep(3)  # Wait for the grid to refresh

def remove_grouping(driver):
    while True:
        icons = driver.find_elements(By.XPATH, "//div[@aria-label='Row Groups']//span[contains(@class,'ag-icon-cancel') and not(contains(@style,'display:none'))]")
        if not icons:
            break
        for ico in icons:
            try:
                driver.execute_script("arguments[0].click();", ico)
            except StaleElementReferenceException:
                continue
        time.sleep(0.2)

def read_csv_data(csv_path):
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df.columns = [c.lower().strip() for c in df.columns]

    pan_airlines_map = {}

    for _, row in df.iterrows():
        pan = row.get("pan", "").strip()
        airline = row.get("airlines", "").strip().lower()
        username = row.get("username", "").strip()
        password = row.get("password", "").strip()

        if not pan or not airline or not username or not password:
            continue  # skip if any important field is missing

        if pan not in pan_airlines_map:
            pan_airlines_map[pan] = []

        if airline not in pan_airlines_map[pan]:
            pan_airlines_map[pan].append(airline)

    print(f"Extracted PAN-Airline map: {pan_airlines_map}")
    return pan_airlines_map

def check_on_airlines(driver, pan_to_check):
    """
    Checks if the PAN is associated with all 5 airlines in the AG Grid.
    This is independent of the credentials in CSV.
    """
    print(f"Checking association of PAN '{pan_to_check}' with all 5 airlines")
    all_airlines = ["klm", "airindia", "aircanada", "airfrance", "lufthansa_swiss"]

    for airline in all_airlines:
        row_xpath = (
            f"//div[contains(@class, 'ag-row') and "
            f".//div[@col-id='airline_name' and translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{airline.lower()}'] and "
            f".//div[@col-id='pan' and normalize-space()='{pan_to_check}']]"
        )

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, row_xpath))
            )
            print(f"✅ PAN association is OK for {airline}")
        except TimeoutException:
            print(f"❌ PAN association FAILED for {airline}")

def pg_status(pan):
    print(f"Checking PG status for PAN: {pan}")
    try:
        with pg_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT valid FROM airlinecreds
                    WHERE pan = %s
                """, (pan,))
                result = cursor.fetchone()
                return result[0] if result else None
    except Exception as e:
        print(f"[DB] Failed to fetch PAN {pan}: {e}")
        return None

def filter_pan(driver):
    """
    Searches for all PANs from the CSV in the AG grid and checks their row presence for all 5 airlines.
    Returns the full pan → airlines mapping from CSV.
    """
    refresh_grid(driver)
    remove_grouping(driver)
    time.sleep(1)

    pan_airlines_map = read_csv_data(CSV_PATH)

    for pan, _ in pan_airlines_map.items():
        try:
            search_pan_elem = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_SEARCH_PAN)))
            search_pan_elem.click()
            search_pan_elem.clear()
            search_pan_elem.send_keys(pan)
            remove_grouping(driver)
            time.sleep(2)
            check_on_airlines(driver, pan)  # Checks presence of all 5 airline rows
        except Exception as e:
            print(f"PAN search not available for {pan}: {e}")

    return pan_airlines_map

def determine_expected_status(pg_status_val, username, password):
    if pg_status_val == "v":
        return "valid"
    elif pg_status_val is None:
        return "pending"
    elif pg_status_val == "":
        if username or password:
            return "wrong credentials"
        else:
            return "not available"
    return "unknown"
# Base row XPath (AG Grid row matcher)
# Base row XPath template (with placeholders for dynamic formatting)
ROW_XPATH_TEMPLATE = (
    "//div[@role='row' and "
    ".//div[@col-id='airline_name' and translate(normalize-space(), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{airline}'] "
    "and .//div[@col-id='pan' and normalize-space()='{pan}']]"
)

# Derived XPath templates for individual cells inside the matched row
X_STATUS_CELL_TEMPLATE = ROW_XPATH_TEMPLATE + "//div[@col-id='0'])]"
X_USERNAME_CELL_TEMPLATE = ROW_XPATH_TEMPLATE + "//div[@col-id='portal_id']"
X_PASSWORD_CELL_TEMPLATE = ROW_XPATH_TEMPLATE + "//div[@col-id='portal_pass']"



def cell_text(driver, template, pan, airline):
    xpath = template.format(pan=pan, airline=airline.lower())
    return driver.find_element(By.XPATH, xpath).text.strip()

def get_status(driver, pan, airline):
    return cell_text(driver, X_STATUS_CELL_TEMPLATE, pan, airline).lower()

def scroll_into_view(driver, xpath):
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )
    driver.execute_script("arguments[0].scrollIntoView({inline: 'center'});", element)
    return element


def wait_for_status_sync(driver, pan, airlines, max_wait=180, poll_interval=5):
    start_time = time.time()
    print(f"⏳ Waiting for status sync for PAN: {pan}")

    while time.time() - start_time < max_wait:
        all_ok = True

        for airline in airlines:
            print(f"\n⏳ Checking airline: {airline}")

            try:
                remove_grouping(driver)
                time.sleep(1)

                status_xpath = X_STATUS_CELL_TEMPLATE.format(pan=pan, airline=airline.lower())
                ag_status_element = scroll_into_view(driver, status_xpath)
                ag_status = ag_status_element.text.strip().lower()
                username = cell_text(driver, X_USERNAME_CELL_TEMPLATE, pan, airline)
                password = cell_text(driver, X_PASSWORD_CELL_TEMPLATE, pan, airline)
                pg_status_val = pg_status(pan)

                print(f"[AG Grid] Status for {airline}: '{ag_status}'")
                print(f"[Postgres] PAN status: '{pg_status_val}'")
                print(f"[CSV] Username: '{username}' | Password: '{password}'")

                expected_status = determine_expected_status(pg_status_val, username, password)

                if ag_status != expected_status:
                    print(f"❌ Status mismatch for {airline} → AG: '{ag_status}' ≠ PG: '{expected_status}'")
                    all_ok = False
                else:
                    print(f"✅ Status match for {airline}")

            except Exception as e:
                print(f"⚠️ Error checking status for {airline}: {e}")
                all_ok = False

        if all_ok:
            elapsed = int(time.time() - start_time)
            print(f"\n✅ All statuses for PAN {pan} are synced across airlines {airlines}.")
            print(f"⏱️ Time taken: {elapsed} seconds.")
            return

        print(f"⏳ Waiting {poll_interval} seconds before next check...")
        time.sleep(poll_interval)

    print(f"\n⚠️ Timeout reached for PAN {pan}. Some airline statuses may not have synced.")
    print(f"⏱️ Total time waited: {int(time.time() - start_time)} seconds.")

# --------------------- Main Flow ---------------------

def main():
    driver = init_driver()
    login_and_pick_workspace(driver)
    upload_csv(driver, CSV_PATH)

    pan_airlines_map = filter_pan(driver)

    for pan, airlines in pan_airlines_map.items():
        print(f"\nPAN found: {pan} airline(s): {airlines}")
        if pan and airlines:
            sync_time = wait_for_status_sync(driver, pan, airlines)
            print(f"\nSync time for PAN {pan}: {sync_time}")
        else:
            print(f"No airline creds found for PAN: {pan}. Skipping status sync.")

    print("\n✅ Done")
    driver.quit()

if __name__ == "__main__":
    main()




# username = 'portal_id'    
# password = 'portal_pass'