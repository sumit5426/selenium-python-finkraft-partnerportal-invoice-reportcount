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
from selenium.common.exceptions import NoSuchElementException

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
X_AIRLINE_FILTER_ICON = "//div[@class='ag-cell-label-container']//span[@ref='eText' and normalize-space()='Airlines']/ancestor::div[contains(@class, 'ag-header-cell')]"

# Base row XPath template
ROW_XPATH_TEMPLATE = (
    "//div[@role='row'"
    " and .//div[@col-id='airline_name' and "
    "translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{airline}']"
    " and .//div[@col-id='pan' and normalize-space()='{pan}']"
    "]"
)

# Derived cell templates
X_USERNAME_CELL_TEMPLATE = ROW_XPATH_TEMPLATE + "//div[@col-id='portal_id']"
X_PASSWORD_CELL_TEMPLATE = ROW_XPATH_TEMPLATE + "//div[@col-id='portal_pass']"

# ------------------------- DRIVER + DB ----------------------------
def init_driver() -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=opts, seleniumwire_options={"verify_ssl": False})
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    time.sleep(1)
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
    wait = WebDriverWait(driver, 16)
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
        time.sleep(2)  # Wait for the page to load after login
        for attempt in range(3):
            try:
                print("Login successful, now selecting workspace...")
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

def filter_pan_and_airline(driver):
    """
    Filters AG grid by PAN (top search) and airline name (AG set filter),
    ensuring only the matching airline(s) are selected for each PAN.
    """
    refresh_grid(driver)
    remove_grouping(driver)
    time.sleep(1)

    pan_airlines_map = read_csv_data(CSV_PATH)

    for pan, airlines in pan_airlines_map.items():
        try:
            # Step 1: Search PAN
            search_pan_elem = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, X_SEARCH_PAN))
            )
            search_pan_elem.click()
            search_pan_elem.clear()
            search_pan_elem.send_keys(pan)
            time.sleep(1)

            # Step 2: Open Airline Filter
            airline_filter_icon = driver.find_element(
                By.XPATH, '//span[text()="Airlines"]/ancestor::div[contains(@class, "ag-cell-label-container")]//span[contains(@class, "ag-icon-menu")]'
            )
            airline_filter_icon.click()
            
            # Step 2 - Click on the Filter tab inside menu
            filter_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span[role='tab'] .ag-icon-filter"))
            )
            filter_tab.click()

            filter_panel = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "ag-filter-body-wrapper"))
            )

            # Step 3: Deselect "Select All"
            select_all_checkbox = filter_panel.find_element(
                By.XPATH, './/div[@ref="eLabel" and normalize-space(text())="(Select All)"]/following-sibling::div//input'
            )
            if select_all_checkbox.is_selected():
                select_all_checkbox.click()

            # Step 4: Select each airline for this PAN
            for airline in airlines:
                print(f"airline name : {airline}")
                mini_filter = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.ag-mini-filter input.ag-input-field-input"))
                )
                mini_filter.clear()
                mini_filter.send_keys(airline)  # <-- airline from CSV, not PAN

                time.sleep(0.5)

                # Locate the label div containing the airline name text
                label_div = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        f'.//div[@class="ag-set-filter-item"]//div[contains(@class,"ag-checkbox-label") and normalize-space(text())="{airline}"]'
                    ))
                )
                # From the label, go to its parent, then find the sibling div with the checkbox wrapper
                checkbox_wrapper = label_div.find_element(By.XPATH, '../div[contains(@class, "ag-wrapper")]')
                checkbox_wrapper.click()
                wrapper_classes = checkbox_wrapper.get_attribute('class')
                if 'ag-checked' in wrapper_classes:
                    print(f"{airline} checkbox is selected")
                else:
                    print(f"Failed to select {airline} checkbox")
            
            remove_grouping(driver)
        except Exception as e:
            print(f"Error filtering PAN {pan}: {e}")

    return pan_airlines_map

# ───────── Postgres helpers ─────────
def pg_status(pan):
    query = "SELECT valid FROM airlinecreds WHERE pan = %s"
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (pan,))
            row = cur.fetchone()

    if not row:
        print(f"[PG STATUS] PAN {pan}: No record found")
        return None

    value = row[0]
    if isinstance(value, bool):
        status = '[V]' if value else '[]'
    else:
        status = str(value).strip().upper() if value is not None else None

    print(f"[PG STATUS] PAN {pan}: {status}")
    return status

def get_credentials(pan, airline, driver=None):
    """Get username/password from PG first; fallback to AG grid if needed."""
    query = "SELECT portal_id, portal_pass FROM airlinecreds WHERE pan = %s AND airline_name = %s"
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (pan, airline))
            row = cur.fetchone()

    if row and any(row):
        username, password = row
        username = username.strip() if username else None
        password = password.strip() if password else None
        print(f"[PG CREDENTIALS] PAN {pan}, Airline {airline}: Username='{username}', Password='{password}'")
        return username, password

    # fallback to AG
    if driver:
        username = cell_text(driver, X_USERNAME_CELL_TEMPLATE, pan, airline, column_header="Username")
        password = cell_text(driver, X_PASSWORD_CELL_TEMPLATE, pan, airline, column_header="Password")
        return username, password

    return None, None

# ───────── Utility functions ─────────
def get_row_xpath(airline, pan):
    return (
        f"//div[@role='row' and contains(normalize-space(), '{pan}') "
        f"and contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{airline.lower()}')]"
    )

def cell_text(driver, xpath_template, pan, airline, column_header=None):
    xpath = xpath_template.format(pan=pan, airline=airline.lower())
    
    for _ in range(20):
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return element.text.strip()
        except TimeoutException:
            if column_header:
                header_container = WebDriverWait(driver, 10).find_element(By.CSS_SELECTOR, ".ag-header-viewport")
                driver.execute_script(
                    "arguments[0].scrollLeft = arguments[0].scrollLeft + 100;", 
                    header_container
                )
                time.sleep(0.5)
            else:
                break
    return None

def get_status_column_index(driver):
    """Step-wise scroll to find 'Status' header and return aria-colindex."""
    header_container = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".ag-header-viewport"))
    )

    # Step-wise scroll
    for scroll_step in range(4):
        headers = driver.find_elements(By.CSS_SELECTOR, ".ag-header-cell")
        visible_headers = [h.text.strip() for h in headers if h.text.strip()]
        print(f"[DEBUG] Scroll step {scroll_step}: Visible headers = {visible_headers}")

        for header in headers:
            if header.text.strip().lower() == "status":
                col_index = header.get_attribute("aria-colindex")
                print(f"[INFO] Found 'Status' header with aria-colindex={col_index}")
                return col_index

        # scroll right
        driver.execute_script("arguments[0].scrollLeft += 200;", header_container)
        time.sleep(0.2)

    raise Exception("Status column not found after scrolling.")


def get_status_for_airline(driver, pan, airlines):
    statuses = {}
    status_col_index = get_status_column_index(driver)

    for airline in airlines:
        try:
            row_xpath = get_row_xpath(airline, pan)
            row_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, row_xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'nearest'});", row_element)

            cell = row_element.find_element(By.CSS_SELECTOR, f'[aria-colindex="{status_col_index}"]')
            status_text = cell.text.strip()
            statuses[airline] = status_text
            print(f"Status for {airline}: {status_text}")
        except Exception as e:
            print(f"⚠️ Could not get status for {airline}: {e}")
            statuses[airline] = None
    return statuses

# ───────── Status comparison ─────────
def statuses_match(pg_val, ag_val, username, password):
    ag_val_norm = (ag_val or "").strip().lower()
    if pg_val is None:
        if username and password:
            return ag_val_norm in ("pending", "not available", "Pending", "Not Available")
    if pg_val == "[V]":
        return ag_val_norm == "valid"
    if pg_val == "[]":
        if username and password:
            return ag_val_norm in ("Wrong Credential", "wrong credential")
        return ag_val_norm == "not available"
    return False

# ───────── Polling loop ─────────
def wait_for_status_sync(driver, pan, airlines, max_wait=80, poll_interval=5):
    start_time = time.time()
    crossed_estimated_time = set()

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)
        print(f"\n[INFO] Checking all airlines for PAN={pan} (Elapsed: {elapsed}s)")

        ag_statuses = get_status_for_airline(driver, pan, airlines)
        all_ok = True

        for airline, ag_status in ag_statuses.items():
            pg_status_val = pg_status(pan)
            username, password = get_credentials(pan, airline, driver)

            expected_status = None
            if pg_status_val == '[V]':
                expected_status = 'valid'
            elif pg_status_val == '[]':
                expected_status = 'wrong credential' if username and password else 'not available'
            elif pg_status_val is None:
                expected_status = 'pending'
            else:
                expected_status = 'not available' if username and password else 'pending'

            print(f"[AG Grid] {airline}: '{ag_status}'")
            print(f"[Postgres] {airline}: '{pg_status_val}' Expected: '{expected_status}'")

            if statuses_match(pg_status_val, ag_status, username, password):
                print(f"✅ Match for {airline}")
                crossed_estimated_time.discard(airline)
            else:
                all_ok = False
                if elapsed > 40 and airline not in crossed_estimated_time:
                    print(f"⚠️ AG Status for {airline} crossed estimated time.")
                    crossed_estimated_time.add(airline)
                else:
                    print(f"❌ Mismatch for {airline}")

        if all_ok:
            print(f"\n✅ All statuses for PAN {pan} are synced correctly.")
            return elapsed

        print(f"⏳ Waiting {poll_interval}s before next check...")
        time.sleep(poll_interval)

    print(f"\n⚠️ Timeout reached for PAN {pan}. Statuses not fully synced.")
    return None

# ───────── Main ─────────
def main():
    driver = init_driver()
    try:
        login_and_pick_workspace(driver)
        upload_csv(driver, CSV_PATH)
        pan_airlines_map = filter_pan_and_airline(driver)

        for pan, airlines in pan_airlines_map.items():
            print(f"\n[INFO] PAN: {pan} Airlines: {airlines}")
            if pan and airlines:
                wait_for_status_sync(driver, pan, airlines)
            else:
                print(f"No airlines for PAN {pan}, skipping.")

        print("\n✅ Done")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

