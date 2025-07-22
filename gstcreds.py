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
class WorkspaceSwitchError(Exception):
    pass

def login_and_pick_workspace(driver):
    wait = WebDriverWait(driver, 15)
    driver.get(PORTAL_URL)
    page_title = driver.title
    print(page_title)
    partner_portal_name = page_title.split("-")[0].strip()
    print("Portal name:" , partner_portal_name)
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

def wait_pg_non_pending(gstin, limit=12, delay=5, threshold=8):
    """
    Polls the PG status for the GSTIN until it's no longer PROCESSING.
    Returns:
        (final_status, is_slow)
    """
    for i in range(limit):
        st = pg_status(gstin)
        print(f" ⏱️ poll {i+1}/{limit} – PG = {st}")
        if st != "PROCESSING":
            is_slow = i + 1 > threshold  # if it took more than 8 tries
            return st, is_slow
        time.sleep(delay)
    # Timeout – still PROCESSING after all tries
    print("--- Poll timeout of processing ---")
    return None, True


def wait_ag_matches(driver, gstin: str, expected: str,
                    tries: int = 6, delay: float = 2.0) -> tuple[bool, bool]:
    """
    Poll AG‑Grid until it shows the expected status for a GSTIN.
    Returns:
        (match_found: bool, is_slow: bool)
    """
    for n in range(1, tries + 1):
        ag = get_status(driver, gstin)
        print(f"   ⏳ AG poll {n}/{tries} – AG status = {ag}")
        if ag == expected:
            is_slow = (n * delay) > 10.0
            return True, is_slow
        time.sleep(delay)
        refresh_and_filter(driver, gstin)
    return False, True  # match not found, also too slow

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
    # 1. Open row
    quick_filter(driver, gstin)
    wait_for_row(driver, gstin)

    # 2. Inline‑edit user & password
    if not edit_cell(driver, X_USERNAME_CELL.format(gstin=gstin), new_user):
        raise RuntimeError("Username inline‑edit failed")
    if not edit_cell(driver, X_PASSWORD_CELL.format(gstin=gstin), new_pass):
        raise RuntimeError("Password inline‑edit failed")

    # 3. Click Save & confirm toast
    WebDriverWait(driver, 4).until(
        EC.element_to_be_clickable((By.XPATH, X_SAVE_BTN))
    ).click()
    print("💾 Save button clicked") 
    WebDriverWait(driver, 1).until(
        EC.visibility_of_element_located(
            (By.XPATH, "//div[contains(@class,'ant-message-success')]")
        )
    )
    print("✅ Success popup appeared")

    # 4. Refresh grid after saving creds
    refresh_and_filter(driver, gstin)
    print("🔁 Grid refreshed after editing creds")

# ───── Main ─────

def main() -> None:
    driver = init_driver()

    summary = {
        "portal": None,
        "workspace": WORKSPACE_NAME,
        "creds_type": "GST",
        "bulk_upload_csv": False,
        "verifier_updated_pg": None,
        "verifier_to_pg_time_ok": None,
        "ag_updated_pg_status": None,
        "ag_update_time_ok": None,
        "cell_edit_success": None,
        "post_edit_pg_ag_sync": None,
        "post_edit_pg_ag_time_ok": None,
        "remarks": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    try:
        # -------------------- LOGIN & WORKSPACE --------------------
        try:
            portal_name = login_and_pick_workspace(driver)
            print("Portal name", portal_name)
            summary["portal"] = portal_name
        except WorkspaceSwitchError as e:
            summary["remarks"].append(str(e))  # "❌ Failed to switch workspace after 3 attempts."
            insert_into_mongo(summary)
            # write_json_summary(summary)
            return

        # -------------------- 1. Bulk Upload --------------------
        try:
            upload_csv(driver, CSV_PATH)
            refresh_grid(driver)
            summary["bulk_upload_csv"] = True
        except Exception as e:
            summary.update({
                "bulk_upload_csv": False,
                "remarks": [f"❌ [Bulk Upload] Failed: {e}"]
            })
            insert_into_mongo(summary)
            # write_json_summary(summary)
            return

        # -------------------- 2. PG + AG Status Check --------------------
        df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df.columns = [c.lower().strip() for c in df.columns]

        verifier_success = True
        verifier_slow = False
        ag_match_success = True
        ag_slow = False

        for rec in df.to_dict(orient="records"):
            gstin = rec["gstin"]
            print(f"\n🔍 GSTIN {gstin}")

            if not (quick_filter(driver, gstin) and wait_for_row(driver, gstin)):
                verifier_success = False
                summary["remarks"].append(f"❌ [Row Load] GSTIN not visible after upload: {gstin}")
                continue

            ag = get_status(driver, gstin)
            pg = (pg_status(gstin) or "").upper()

            if ag == "pending":
                pg, pg_slow = wait_pg_non_pending(gstin)
                pg = (pg or "").upper()
                refresh_and_filter(driver, gstin)
                ag = get_status(driver, gstin)

                if not pg:
                    verifier_success = False
                    summary["remarks"].append(f"❌ [PG Pending Timeout] for {gstin}")
                    continue
                if pg_slow:
                    verifier_slow = True

            username = get_username(driver, gstin)
            expected = resolve_expected_ag(pg, username)

            if ag != expected or ag == "pending":
                ag_match_success = False
                summary["remarks"].append(
                    f"❌ [PG → AG Mismatch] GSTIN {gstin} → AG: '{ag}' ≠ Expected: '{expected}'"
                )
            else:
                _, ag_delay = wait_ag_matches(driver, gstin, expected)
                if ag_delay:
                    ag_slow = True

        summary.update({
            "verifier_updated_pg": verifier_success,
            "verifier_to_pg_time_ok": not verifier_slow,
            "ag_updated_pg_status": ag_match_success,
            "ag_update_time_ok": not ag_slow
        })

        if not verifier_success:
            summary["remarks"].append("❌ [Verifier → PG] PG not updated for some GSTINs.")
        if verifier_slow:
            summary["remarks"].append("⚠️ [Verifier → PG Timing] PG update was slow.")
        if not ag_match_success:
            summary["remarks"].append("❌ [PG → AG] AG status mismatch for some GSTINs.")
        if ag_slow:
            summary["remarks"].append("⚠️ [PG → AG Timing] AG update was slow.")

        # If major failure, skip edit step
        if not verifier_success or not ag_match_success:
            insert_into_mongo(summary)
            # write_json_summary(summary)
            return

        # -------------------- 3. Edit Flow --------------------
        print(f"\n🖊️ Editing {EDIT_GSTIN}")
        try:
            edit_creds_in_grid(driver, EDIT_GSTIN, NEW_USERNAME, NEW_PASSWORD)
            summary["cell_edit_success"] = True

            pg_final, pg_slow = wait_pg_non_pending(EDIT_GSTIN)
            if pg_final is None:
                raise RuntimeError("PG still pending after timeout")

            expected = resolve_expected_ag(pg_final, get_username(driver, EDIT_GSTIN))
            refresh_and_filter(driver, EDIT_GSTIN)
            ag_final = get_status(driver, EDIT_GSTIN)
            matched, ag_slow = wait_ag_matches(driver, EDIT_GSTIN, expected)

            summary["post_edit_pg_ag_sync"] = (ag_final == expected)
            summary["post_edit_pg_ag_time_ok"] = not (pg_slow or ag_slow)

            if pg_slow:
                summary["remarks"].append("⚠️ [Post-Edit PG Timing] PG update slow.")
            if ag_slow:
                summary["remarks"].append("⚠️ [Post-Edit AG Timing] AG update slow.")
            if ag_final != expected:
                summary["remarks"].append(
                    f"❌ [Post-Edit] AG mismatch → AG: {ag_final}, Expected: {expected}"
                )

        except Exception as e:
            summary.update({
                "cell_edit_success": False,
                "post_edit_pg_ag_sync": None,
                "post_edit_pg_ag_time_ok": None
            })
            summary["remarks"].append(f"❌ [Edit] Failed for {EDIT_GSTIN}: {e}")

        # Final Mongo Insert
        insert_into_mongo(summary)
        # write_json_summary(summary)
        trigger_creds()
        print("Mail Sent")

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()