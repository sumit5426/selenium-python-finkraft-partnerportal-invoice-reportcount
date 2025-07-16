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
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, StaleElementReferenceException
from psycopg2 import sql
from insert_mongo import insert_into_mongo, prepare_report, write_json_summary

# ------------------- 1.  CONFIGURATION --------------------------#
load_dotenv()

PORTAL_URL       = "https://myyatra.finkraft.ai/auth/signin"
WORKSPACE_NAME   = "Test123"
CSV_PATH         = "gst_creds_1.csv"

PG_HOST          = "postgres.centralindia.cloudapp.azure.com"
PG_PORT          = 5432
PG_DATABASE      = "gstservice_db"
PG_USER          = os.getenv("PG_DB_USERNAME")
PG_PASSWORD      = os.getenv("PG_DB_PASSWORD")

LOGIN_USERNAME   = os.getenv("LOGIN_USERNAME")
LOGIN_PASSWORD   = os.getenv("LOGIN_PASSWORD")

X_CREDENTIALS_TAB  = "//div[contains(@class,'MenuItem')]//p[normalize-space()='Credentials']"
X_GST_TAB          = "//div[@class='ant-tabs-tab-btn' and text()='GST']"
X_BULK_UPLOAD_BTN  = "//button[@id='bulkUpdateBtn' and .//span[text()='Bulk Upload']]"
X_FILE_INPUT       = "//input[@type='file']"
X_SUBMIT_BTN       = "//button[contains(@class,'ant-btn') and .//span[text()='Submit']]"
X_SEARCH_BOX       = "//input[@placeholder='Search GSTIN or Username']"

COL_GSTIN    = "gstin"
COL_USERNAME = "username"
COL_PASSWORD = "password"

# X_SUCCESS_POPUP = 'Changes saved successfully!'
X_SUCCESS_POPUP = "//*[contains(@class, 'ant-message-success')]"


ROW_XPATH = ("//div[@role='row' and "
    ".//div[@col-id='gstin' and contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
    " '{gstin}')] ]")

X_STATUS_CELL = ROW_XPATH + "//div[@col-id='status']"
X_USERNAME_CELL = ROW_XPATH + "//div[@col-id='username']"
X_PASSWORD_CELL = ROW_XPATH + "//div[@col-id='password']"

EDIT_GSTIN      = "12WUTYH1234P1ZC"
NEW_USERNAME    = "edit_user_12"
NEW_PASSWORD    = "edit_pass@12345"
X_SAVE_BTN      = "//button[@id='saveBtn']"

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
    page_title = driver.title
    print(page_title)
    partner_portal_name = page_title.split("-")[0].strip()
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

def upload_csv(driver, csv_path):
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()
    WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.XPATH, X_BULK_UPLOAD_BTN))).click()
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, X_FILE_INPUT))).send_keys(os.path.abspath(csv_path))
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SUBMIT_BTN))).click()
    time.sleep(2)

def refresh_grid(driver):
    driver.refresh()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()

def refresh_and_filter(driver, gstin):
    refresh_grid(driver)
    if not quick_filter(driver, gstin):
        raise RuntimeError(f"Gstin {gstin} row not visible after filter")
    wait_for_row(driver, gstin)

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

def quick_filter(driver, gstin, attempts=3):
    gstin = gstin.strip().replace("\u00a0", "")
    for n in range(1, attempts + 1):
        remove_grouping(driver)
        box = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SEARCH_BOX)))
        box.send_keys(Keys.CONTROL, "a", Keys.DELETE)
        driver.execute_script("arguments[0].value='';", box)
        box.send_keys(gstin)
        time.sleep(1.0)
        remove_grouping(driver)
        row_xpath = ROW_XPATH.format(gstin=gstin)
        try:
            WebDriverWait(driver, 4).until(EC.visibility_of_element_located((By.XPATH, row_xpath)))
            return True
        except TimeoutException:
            refresh_grid(driver)
    return False

def wait_for_row(driver, gstin, timeout=8):
    row_xpath = ROW_XPATH.format(gstin=gstin.strip().replace("\u00a0", ""))
    try:
        WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.XPATH, row_xpath)))
        return True
    except TimeoutException:
        return False

def cell_text(driver, template, gstin):
    return driver.find_element(By.XPATH, template.format(gstin=gstin)).text.strip()

def get_status(driver, gstin):
    return cell_text(driver, X_STATUS_CELL, gstin).lower()

def get_username(driver, gstin):
    return cell_text(driver, X_USERNAME_CELL, gstin)

def get_password(driver, gstin):
    return cell_text(driver, X_PASSWORD_CELL, gstin)

# ───── Postgres Helpers ─────

def pg_status(gstin):
    with pg_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM gstcreds WHERE gstin=%s", (gstin,))
        row = cur.fetchone()
        return row[0].upper() if row else "UNKNOWN"

def wait_pg_non_pending(gstin, limit=12, delay=5):
    for i in range(limit):
        st = pg_status(gstin)
        print(f" ⏱️ poll {i+1}/{limit} – PG = {st}")
        if st != "PENDING":
            return st
        time.sleep(delay)
    return None

def wait_pg_become_pending(gstin, limit=6, delay=4):
    for i in range(limit):
        st = pg_status(gstin)
        print(f" ⏳ waiting for PENDING {i + 1}/{limit} – PG status = {st}")
        if st == "PENDING":
            return True
        time.sleep(delay)
    return False

def wait_ag_matches(driver, gstin: str, expected: str,
                    tries: int = 6, delay: float = 3.0) -> bool:
    """
    After PG moved to a final state, poll AG‑Grid until the cell
    shows the expected text. Returns True if match found.
    """
    for n in range(1, tries + 1):
        ag = get_status(driver, gstin)
        print(f"   ⏳ AG poll {n}/{tries} – AG status = {ag}")
        if ag == expected:
            return True
        time.sleep(delay)
        # a light refresh helps AG re‑query its data‑source
        refresh_and_filter(driver, gstin)
    return False



# ───── Editing ─────

def edit_cell(driver, cell_xpath: str, new_val: str, retries: int = 3) -> bool:
    for _ in range(retries):
        cell = driver.find_element(By.XPATH, cell_xpath)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell)
        ActionChains(driver).double_click(cell).perform()
        active = driver.switch_to.active_element
        active.send_keys(Keys.CONTROL, "a", Keys.DELETE, Keys.ENTER)
        time.sleep(1)
        ActionChains(driver).double_click(cell).perform()
        active = driver.switch_to.active_element
        active.send_keys(new_val, Keys.ENTER)
        time.sleep(1.2)
        current = cell.text.strip()
        print(f"🔎 Cell text after edit: '{current}'  (expected: '{new_val}')")
        if new_val.endswith(current[-3:]):  # match last 3 chars (masked password)
            return True
    return False

def edit_creds_in_grid(driver, gstin, new_user, new_pass):
    # 1. open row
    quick_filter(driver, gstin)
    wait_for_row(driver, gstin)

    # 2. inline‑edit user & password
    if not edit_cell(driver, X_USERNAME_CELL.format(gstin=gstin), new_user):
        raise RuntimeError("Username inline‑edit failed")
    if not edit_cell(driver, X_PASSWORD_CELL.format(gstin=gstin), new_pass):
        raise RuntimeError("Password inline‑edit failed")

    # 3. click Save & confirm toast
    WebDriverWait(driver, 4).until(
        EC.element_to_be_clickable((By.XPATH, X_SAVE_BTN))
    ).click()
    print("💾 Save button clicked")

    WebDriverWait(driver, 6).until(
        EC.visibility_of_element_located(
            (By.XPATH, "//div[contains(@class,'ant-message-success')]")
        )
    )
    print("✅ Success popup appeared")

    # 4. first refresh/search → AG = pending
    refresh_and_filter(driver, gstin)

    # 5. poll PG until NOT pending
    pg_final = wait_pg_non_pending(gstin)
    print(f"📬 PG resolved to: {pg_final}")

    # 6. final refresh/search & compare
    refresh_and_filter(driver, gstin)
    ag_final = get_status(driver, gstin)
    print(f"📋 AG: {ag_final}  |  PG: {pg_final}")

    expected = (
        "error verifying" if pg_final == "EXCEPTION" else
        "valid"           if pg_final == "ACTIVE"    else
        ("wrong credential" if pg_final == "INVALID" and get_username(driver, gstin)
         else "not available") if pg_final == "INVALID" else
        "pending"
    )

    if ag_final != expected:
        raise RuntimeError("❌ Post‑edit mismatch")
    print("🎯 ✅ AG matches PG → edit successful")


# ───── Main ─────

def main() -> None:
    driver = init_driver()
    summary = {
        "portal": "Finkraft",
        "workspace": WORKSPACE_NAME,
        "creds_type": "GST",
        "status": True,            # flipped on first error
        "bulk_upload_success": True,
        "edit_success": False,     # set to True if edit flow passes
        "remarks": [],
        "results": [],             # <- every GSTIN result will be appended here
        "timestamp": datetime.utcnow().isoformat()
    }

    try:
        login_and_pick_workspace(driver)

        # -------------- bulk upload -----------------
        try:
            upload_csv(driver, CSV_PATH)
            refresh_grid(driver)
        except Exception as e:
            summary["bulk_upload_success"] = False
            summary["status"] = False
            summary["remarks"].append(f"Bulk upload failed: {e}")
            raise                                          # abort early

        # ---------- initial validation loop ----------
        df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df.columns = [c.lower().strip() for c in df.columns]

        for rec in df.to_dict(orient="records"):
            gstin = rec["gstin"]
            print(f"\n🔍 GSTIN {gstin}")

            if not (quick_filter(driver, gstin) and wait_for_row(driver, gstin)):
                summary["status"] = False
                summary["remarks"].append(f"{gstin}: row not visible after upload")
                summary["results"].append((gstin, "N/A", pg_status(gstin)))
                continue

            ag = get_status(driver, gstin)
            pg = pg_status(gstin)

            if ag == "pending":
                pg = wait_pg_non_pending(gstin)
                refresh_and_filter(driver, gstin)
                ag = get_status(driver, gstin)

            expected = (
                "error verifying" if pg == "EXCEPTION" else
                "valid"           if pg == "ACTIVE"    else
                ("wrong credential" if pg == "INVALID" and get_username(driver, gstin)
                 else "not available") if pg == "INVALID" else
                "pending"
            )

            if ag != expected:
                summary["status"] = False
                summary["remarks"].append(f"{gstin}: AG '{ag}' ≠ expected '{expected}'")

            # >>> append per‑gstin triple right here
            summary["results"].append((gstin, ag, pg))

        # -------------- edit flow -------------------
        print(f"\n🖊️ Editing {EDIT_GSTIN}")
        try:
            edit_creds_in_grid(driver, EDIT_GSTIN, NEW_USERNAME, NEW_PASSWORD)
            summary["edit_success"] = True
        except Exception as e:
            summary["status"] = False
            summary["edit_success"] = False
            summary["remarks"].append(f"Edit flow failed: {e}")

    finally:
        # ------------- store + quit -----------------
        try:
            insert_into_mongo(summary)         # no‑op if URI unset
        except Exception as e:
            print("⚠️ Mongo insert failed:", e)

        write_json_summary(summary)            # always write summary.json

        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()