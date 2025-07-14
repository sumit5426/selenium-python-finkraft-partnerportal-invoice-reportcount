"""
End‑to‑end GSTIN bulk‑upload & credential‑sync runner
----------------------------------------------------
pip install selenium selenium-wire psycopg2-binary pandas python-dotenv
"""

import os
import time
from datetime import datetime
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.common.exceptions import TimeoutException , StaleElementReferenceException


# ------------------- 1.  CONFIGURATION --------------------------#
load_dotenv()                                               # .env in project root

PORTAL_URL       = "https://myyatra.finkraft.ai/auth/signin"
WORKSPACE_NAME   = "Test123"
CSV_PATH         = "gst_creds_1.csv"                        # path to upload file

PG_HOST          = "postgres.centralindia.cloudapp.azure.com"
PG_PORT          = 5432
PG_DATABASE      = "gstservice_db"
PG_USER          = os.getenv("PG_DB_USERNAME")
PG_PASSWORD      = os.getenv("PG_DB_PASSWORD")

LOGIN_USERNAME   = os.getenv("LOGIN_USERNAME")
LOGIN_PASSWORD   = os.getenv("LOGIN_PASSWORD")

# --- Grid‑specific XPath constants (tweak if your UI differs) -----------------
X_CREDENTIALS_TAB  = "//div[contains(@class,'MenuItem')]//p[normalize-space()='Credentials']"
X_GST_TAB          = "//div[@class='ant-tabs-tab-btn' and text()='GST']"
X_BULK_UPLOAD_BTN  = "//button[@id='bulkUpdateBtn' and .//span[text()='Bulk Upload']]"
X_FILE_INPUT       = "//input[@type='file']"
X_SUBMIT_BTN       = "//button[contains(@class,'ant-btn') and .//span[text()='Submit']]"

X_SEARCH_BOX       = "//input[@placeholder='Search GSTIN or Username']"
# These three refer to the *headers* in your CSV / DataFrame
COL_GSTIN    = "gstin"      # lowercase because we normalised df.columns
COL_USERNAME = "username"
COL_PASSWORD = "password"

# Dynamic row‑relative XPaths:
# ROW_XPATH          = ("//div[@role='row' and .//div[@col-id='gstin' and ""normalize-space(text())='{gstin}']]")
ROW_XPATH = (
    "//div[@role='row' and "
    ".//div[@col-id='gstin' and contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
    " '{gstin}')] ]"
)
X_STATUS_CELL   = ROW_XPATH + "//div[@col-id='status']"
X_USERNAME_CELL = ROW_XPATH + "//div[@col-id='username']"
X_PASSWORD_CELL = ROW_XPATH + "//div[@col-id='password']"


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
def login_and_pick_workspace(driver):
    wait = WebDriverWait(driver, 15)
    driver.get(PORTAL_URL)

    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Email']"))).send_keys(LOGIN_USERNAME)
    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))).click()

    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Password']"))).send_keys(LOGIN_PASSWORD)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

    # for attempt in range(3):
    #     try:
    #         wait.until(EC.element_to_be_clickable(
    #             (By.XPATH, "//div[contains(@class,'ant-dropdown-trigger')]"))).click()
    #         ws_el = wait.until(EC.element_to_be_clickable((
    #             By.XPATH, f"//p[normalize-space()='{WORKSPACE_NAME}']")))
    #         try:
    #             ws_el.click()
    #         except ElementClickInterceptedException:
    #             driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ws_el)
    #             ws_el.click()
    #         return
    #     except Exception:
    #         if attempt < 2:
    #             driver.refresh()
    #         else:
    #             raise RuntimeError("Could not choose workspace")

# ------------------------- UI Helpers -----------------------------
def upload_csv(driver, csv_path):
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()
    Bulk_upload = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_BULK_UPLOAD_BTN)))
    time.sleep(2)  # short delay to let UI settle
    Bulk_upload.click()
    file_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, X_FILE_INPUT)))
    file_input.send_keys(os.path.abspath(csv_path))
    print("📂 CSV chosen")
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SUBMIT_BTN))).click()
    print("✅ CSV uploaded")

def refresh_grid(driver):
    driver.refresh()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()

# def remove_grouping(driver):
#     wait = WebDriverWait(driver, 3)
#     try:
#         while True:
#             cancel_icon = wait.until(
#                 EC.element_to_be_clickable((By.XPATH,
#                     "//div[@aria-label='Row Groups']//span[contains(@class,'ag-icon-cancel') and not(contains(@style,'display:none'))]"
#                 )))
#             cancel_icon.click()
#             wait.until_not(EC.staleness_of(cancel_icon))
#     except TimeoutException:
#         pass


def remove_grouping(driver):
    """
    Click the × icon in the Row‑Groups panel and wait until
    no cancel icons remain. Safe to call even when nothing is grouped.
    """
    wait = WebDriverWait(driver, 3)
    while True:
        try:
            cancel_icons = driver.find_elements(By.XPATH,
                "//div[@aria-label='Row Groups']//span[contains(@class,'ag-icon-cancel') and not(contains(@style,'display:none'))]"
            )
            if not cancel_icons:
                break  # no more groupings

            for icon in cancel_icons:
                try:
                    driver.execute_script("arguments[0].click();", icon)
                    time.sleep(0.5)  # let it update
                except StaleElementReferenceException:
                    continue  # element went stale, try next
        except Exception:
            break

# def quick_filter(driver, gstin: str, max_attempts=3):
#     for attempt in range(max_attempts):
#         remove_grouping(driver)
#         search = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SEARCH_BOX)))
#         search.click()
#         gstin_clean = gstin.strip().replace(" ", "")   # also removes NBSP (U+00A0)
#         search.send_keys(Keys.CONTROL, "a", Keys.DELETE)
#         driver.execute_script("arguments[0].value='';", search)
#         gstin_clean = gstin.strip().replace(" ", "")
#         search.send_keys(gstin)
#         time.sleep(1.5)
#         remove_grouping(driver)

#         if wait_for_grid_row(driver, gstin):
#             print(f"✅ GSTIN {gstin} found in grid.")
#             return True
#         else:
#             print(f"🚫 GSTIN {gstin} not found after retries.")
#             return False
#     return False

# def wait_for_grid_row(driver, gstin, timeout=10, retries=3):
#     row_xpath = ROW_XPATH.format(gstin=gstin)
#     for attempt in range(retries + 1):
#         try:
#             WebDriverWait(driver, timeout).until(
#                 EC.visibility_of_element_located((By.XPATH, row_xpath)))
#             return True
#         except TimeoutException:
#             if attempt < retries:
#                 # Hard refresh + re‑filter
#                 refresh_table_and_filter(driver, gstin)
#             else:
#                 return False

def quick_filter(driver, gstin: str, max_attempts: int = 3) -> bool:
    """
    Type `gstin` into the AG‑Grid quick‑filter.
    Returns True if the row becomes visible, False otherwise.
    """
    gstin_clean = gstin.strip().replace(" ", "")        # remove spaces + NBSP

    for attempt in range(1, max_attempts + 1):
        remove_grouping(driver)                         # clear any grouping chip

        # focus the search box
        search = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, X_SEARCH_BOX))
        )
        search.click()

        # clear previous value
        search.send_keys(Keys.CONTROL, "a", Keys.DELETE)
        driver.execute_script("arguments[0].value='';", search)

        # type cleaned GSTIN
        search.send_keys(gstin_clean)
        time.sleep(1.2)                                 # debounce wait
        remove_grouping(driver)                         # grouping often re‑appears

        # did the row render?
        row_xpath = ROW_XPATH.format(gstin=gstin_clean)
        try:
            WebDriverWait(driver, 4).until(
                EC.visibility_of_element_located((By.XPATH, row_xpath))
            )
            print(f"🔍 GSTIN {gstin} visible in grid (attempt {attempt})")
            return True
        except TimeoutException:
            print(f"↻ attempt {attempt}/{max_attempts}: row not visible yet")
            driver.execute_script("window.scrollTo(0, 0);")  # ensure viewport reset

    return False  # all attempts exhausted


def wait_for_grid_row(driver, gstin, timeout=10, max_retries=3):
    print(f"checking for {gstin} in grid")
    # row_xpath = f"//div[@role='row' and .//div[@col-id='gstin' and contains(text(), '{gstin}')]]"
    row_xpath = ROW_XPATH.format(gstin=gstin.upper())

    for attempt in range(max_retries):
        try:
            WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.XPATH, row_xpath))
            )
            return True
        except TimeoutException:
            print(f"⚠️  Attempt {attempt + 1}/{max_retries}: Row for {gstin} not found. Refreshing...")
            refresh_grid(driver)
    return False


def get_status_text(driver, gstin):
    print(f"Status of {gstin} in ag")
    return driver.find_element(By.XPATH, X_STATUS_CELL.format(gstin=gstin)).text.strip()

def get_username_text(driver, gstin):
    return driver.find_element(By.XPATH, X_USERNAME_CELL.format(gstin=gstin)).text.strip()

def get_password_text(driver, gstin):
    return driver.find_element(By.XPATH, X_PASSWORD_CELL.format(gstin=gstin)).text.strip()

def refresh_table_and_filter(driver, gstin):
    refresh_grid(driver)
    quick_filter(driver, gstin)
    wait_for_grid_row(driver, gstin)

# ------------------------- STATUS CHECK -----------------------------
def fetch_status_from_db(gstin):
    with pg_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM gstcreds WHERE gstin = %s", (gstin,))
        row = cur.fetchone()
        return row[0].upper() if row else "UNKNOWN"

def wait_for_final_status(gstin, retries=5, delay=5):
    for _ in range(retries):
        status = fetch_status_from_db(gstin)
        if status in {"ACTIVE", "INVALID", "EXCEPTION"}:
            return status
        time.sleep(delay)
        print(f"Staus of gstin in PG {gstin} - {status}")
    return "PENDING"

# ------------------------- MAIN -----------------------------
def main():
    driver = init_driver()
    try:
        login_and_pick_workspace(driver)
        upload_csv(driver, CSV_PATH)
        refresh_grid(driver)

        df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df.columns = [c.lower().strip() for c in df.columns]
        records = df.to_dict(orient="records")

        for rec in records:
            gstin = rec["gstin"]
            quick_filter(driver, gstin)
            if not wait_for_grid_row(driver, gstin):
                continue

            current_status = get_status_text(driver, gstin).lower()
            if current_status != "pending":
                continue

            db_status = wait_for_final_status(gstin)
            print(f"DB Status - {db_status} ")
            refresh_table_and_filter(driver, gstin)

            ag_status = get_status_text(driver, gstin).lower()

            if db_status == "EXCEPTION":
                expected = "error verifying"
            elif db_status == "ACTIVE":
                expected = "valid"
            elif db_status == "INVALID":
                username = get_username_text(driver, gstin)
                password = get_password_text(driver, gstin)
                expected = "wrong credential" if username and password else "not available"
            else:
                expected = "pending"

            if ag_status != expected:
                print(f"❌ {gstin}: expected '{expected}', got '{ag_status}'")
            else:
                print(f"✅ {gstin}: status OK - expected '{expected}', got '{ag_status}'")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()






