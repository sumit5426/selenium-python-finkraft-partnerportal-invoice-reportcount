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
from psycopg2 import sql
from insert_mongo import prepare_report, insert_into_mongo, write_json_summary

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
# X_USERNAME_CELL = ROW_XPATH + "//div[@role='gridcell' and @col-id='username']"
# X_PASSWORD_CELL = ROW_XPATH + "//div[@role='gridcell' and @col-id='password']"
X_USERNAME_CELL = (
    "//div[@role='row' and .//div[@col-id='gstin' and contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{gstin}')]]"
    "//div[@role='gridcell' and @col-id='username']"
)

X_PASSWORD_CELL = (
    "//div[@role='row' and .//div[@col-id='gstin' and contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{gstin}')]]"
    "//div[@role='gridcell' and @col-id='password']"
)


# ⇒ which GSTIN we edit after initial verification
EDIT_GSTIN      = "12WUTYH1234P1ZC"
NEW_USERNAME    = "edit_user"
NEW_PASSWORD    = "edit_pass@123"

X_SAVE_BTN  = "//button[@id='saveBtn']"

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
    
    # Step 1: Load portal
    driver.get(PORTAL_URL)
    wait.until(lambda d: d.title.strip())  # wait until title is non-empty
    page_title = driver.title
    print(f"🔖 Page title: {page_title}")

    # Step 2: Extract portal name
    partner_portal_name = page_title.split("-")[0].strip() if "-" in page_title else page_title.strip()

    # Step 3: Login process
    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Email']"))).send_keys(LOGIN_USERNAME)
    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))).click()

    wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Password']"))).send_keys(LOGIN_PASSWORD)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

    # Step 4: Attempt to pick workspace (with retries)
    for attempt in range(3):
        try:
            dropdown = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@class,'ant-dropdown-trigger')]")))
            dropdown.click()

            ws_el = wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//p[normalize-space()='{WORKSPACE_NAME}']")))
            try:
                ws_el.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ws_el)
                ws_el.click()

            print(f"✅ Workspace '{WORKSPACE_NAME}' selected.")
            break
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} to select workspace failed: {e}")
            if attempt < 2:
                driver.refresh()
            else:
                raise RuntimeError("❌ Could not choose workspace after 3 attempts.")

    # Step 5: Return partner/portal name for use in prepare_report()
    return partner_portal_name

def upload_csv(driver, csv_path):
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()
    WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.XPATH, X_BULK_UPLOAD_BTN))).click()
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, X_FILE_INPUT))
                     ).send_keys(os.path.abspath(csv_path))
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, X_SUBMIT_BTN))).click()
    time.sleep(2)  # allow modal to close


def refresh_grid(driver):
    driver.refresh()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_CREDENTIALS_TAB))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, X_GST_TAB))).click()


def remove_grouping(driver):
    while True:
        icons = driver.find_elements(
            By.XPATH,
            "//div[@aria-label='Row Groups']"
            "//span[contains(@class,'ag-icon-cancel') and not(contains(@style,'display:none'))]"
        )
        if not icons:
            break
        for ico in icons:
            try:
                driver.execute_script("arguments[0].click();", ico)
            except StaleElementReferenceException:
                continue
        time.sleep(0.2)


def quick_filter(driver, gstin, attempts=3):
    gstin = gstin.strip().replace(" ", "")
    for n in range(1, attempts + 1):
        remove_grouping(driver)
        box = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, X_SEARCH_BOX))
        )
        box.send_keys(Keys.CONTROL, "a", Keys.DELETE)
        driver.execute_script("arguments[0].value='';", box)
        box.send_keys(gstin)
        time.sleep(1.0)
        remove_grouping(driver)
        row_xpath = ROW_XPATH.format(gstin=gstin)
        try:
            WebDriverWait(driver, 4).until(
                EC.visibility_of_element_located((By.XPATH, row_xpath)))
            return True
        except TimeoutException:
            refresh_grid(driver)
    return False


def wait_for_row(driver, gstin, timeout=8):
    row_xpath = ROW_XPATH.format(gstin=gstin.strip().replace(" ", ""))
    try:
        WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, row_xpath)))
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


def refresh_and_filter(driver, gstin):
    refresh_grid(driver)
    quick_filter(driver, gstin)
    wait_for_row(driver, gstin)


# ───────────── PG helpers ─────────────
def pg_status(gstin):
    with pg_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM gstcreds WHERE gstin=%s", (gstin,))
        row = cur.fetchone()
        return row[0].upper() if row else "UNKNOWN"


def wait_pg_non_pending(gstin, limit=12, delay=5):
    for i in range(limit):
        st = pg_status(gstin)
        print(f" ⏱️  poll {i + 1}/{limit} – PG status = {st}")
        if st != "PENDING":
            return st
        time.sleep(delay)
    return "PENDING"


def wait_pg_become_pending(gstin, limit=6, delay=4):
    """After an edit we expect PG to reset to PENDING."""
    for i in range(limit):
        st = pg_status(gstin)
        print(f" ⏳ waiting for PENDING {i + 1}/{limit} – PG status = {st}")
        if st == "PENDING":
            return True
        time.sleep(delay)
    return False

def edit_cell(driver, cell_xpath: str, new_val: str, retries: int = 3) -> bool:
    for _ in range(retries):
        cell = driver.find_element(By.XPATH, cell_xpath)
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cell)

        # 1️⃣  First pass: clear & commit empty
        ActionChains(driver).double_click(cell).perform()
        active = driver.switch_to.active_element
        active.send_keys(Keys.CONTROL, "a", Keys.DELETE, Keys.ENTER)
        time.sleep(1)                     # allow grid to commit empty value

        # 2️⃣  Second pass: enter new value
        ActionChains(driver).double_click(cell).perform()
        active = driver.switch_to.active_element
        active.send_keys(new_val, Keys.ENTER)
        time.sleep(1.2)                     # let grid update

        # 3️⃣  Verify
        current = cell.text.strip()
        print(f"🔎 Cell text after edit: '{current}'  (expected: '{new_val}')")
        if current == new_val:
            return True
    return False  

def edit_creds_in_grid(driver, gstin, new_user, new_pass):
    row_xpath = ROW_XPATH.format(gstin=gstin)
    WebDriverWait(driver, 8).until(
        EC.visibility_of_element_located((By.XPATH, row_xpath)))

    ok_user = edit_cell(driver, X_USERNAME_CELL.format(gstin=gstin), new_user)
    ok_pass = edit_cell(driver, X_PASSWORD_CELL.format(gstin=gstin), new_pass)

    # ✅  click Save
    try:
        save_btn = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable((By.XPATH, X_SAVE_BTN))
        )
        save_btn.click()
        time.sleep(1)   # let grid commit row
    except TimeoutException:
        print("⚠️  Save button not found / click skipped")

    # Verify after Save
    final_user = get_username(driver, gstin)
    final_pass = get_password(driver, gstin)
    if final_user == new_user and final_pass.endswith(new_pass[-3:]):  # grid may mask pw
        print(f"✏️  Edited creds for {gstin} → {new_user}/{new_pass}")
    else:
        raise RuntimeError(f"Failed to persist edit for {gstin}")

def delete_from_pg(csv_path: str,
                       statuses_to_delete=("INVALID", "EXCEPTION")) -> None:
    """
    Delete GSTIN rows that are present in csv_path AND have a PG status
    in statuses_to_delete (default: INVALID, EXCEPTION).
    """
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    gstins = tuple(df["GSTIN"].str.strip())

    if not gstins:
        print("⚠️  CSV had no GSTINs; nothing to purge.")
        return

    with pg_connect() as conn, conn.cursor() as cur:
        query = sql.SQL(
            "DELETE FROM gstcreds "
            "WHERE gstin = ANY(%s) "
            "  AND UPPER(status) = ANY(%s);"
        )
        cur.execute(query, (list(gstins), list(statuses_to_delete)))
        deleted = cur.rowcount
        conn.commit()

    print(f"🗑️  Purged {deleted} rows from gstcreds "
          f"with status in {statuses_to_delete}")

# ───────────── MAIN ─────────────
def main():
    driver = init_driver()
    try:
        portal_name = login_and_pick_workspace(driver)

        # 1️⃣  upload CSV once
        print("📤 Uploading full CSV…")
        upload_csv(driver, CSV_PATH)
        refresh_grid(driver)

        # 2️⃣  process each GSTIN
        df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df.columns = [c.lower().strip() for c in df.columns]
        for rec in df.to_dict(orient="records"):
            gstin = rec["gstin"]
            print(f"\n🔍 GSTIN {gstin}")

            if not quick_filter(driver, gstin) or not wait_for_row(driver, gstin):
                print(f"❌ Row not found"); continue

            ag_stat = get_status(driver, gstin)
            if ag_stat == "pending":
                pg_stat = wait_pg_non_pending(gstin)
                refresh_and_filter(driver, gstin)
                ag_stat = get_status(driver, gstin)
            else:
                pg_stat = pg_status(gstin)

            # expected text mapping
            if pg_stat == "EXCEPTION":
                expected = "error verifying"
            elif pg_stat == "ACTIVE":
                expected = "valid"
            elif pg_stat == "INVALID":
                expected = ("wrong credential"
                            if get_username(driver, gstin) else "not available")
            else:
                expected = "pending"

            if ag_stat != expected:
                print(f"❌ {gstin}: AG '{ag_stat}' ≠ expected '{expected}'")
            else:
                print(f"✅ {gstin}: AG matches PG ({ag_stat})")

        # 3️⃣  edit one GSTIN
        print(f"\n🖊️  Editing creds for {EDIT_GSTIN}")
        quick_filter(driver, EDIT_GSTIN); wait_for_row(driver, EDIT_GSTIN)
        edit_creds_in_grid(driver, EDIT_GSTIN, NEW_USERNAME, NEW_PASSWORD)

        # wait until PG resets to PENDING
        if wait_pg_become_pending(EDIT_GSTIN):
            print("🔁 PG reset to PENDING after edit")
        else:
            print("⚠️  PG did not reset to PENDING; continuing anyway")

        # wait again until PG non‑pending
        pg_final = wait_pg_non_pending(EDIT_GSTIN)
        refresh_and_filter(driver, EDIT_GSTIN)
        ag_final = get_status(driver, EDIT_GSTIN)

        if pg_final == "EXCEPTION":
            expected_final = "error verifying"
        elif pg_final == "ACTIVE":
            expected_final = "valid"
        elif pg_final == "INVALID":
            expected_final = ("wrong credential"
                              if get_username(driver, EDIT_GSTIN) else "not available")
        else:
            expected_final = "pending"

        if ag_final != expected_final:
            print(f"❌ After edit: AG '{ag_final}' ≠ expected '{expected_final}'")
        else:
            print(f"✅ After edit: AG '{ag_final}' == PG '{pg_final}'")    

    # ---------- summary / cleanup ----------
    finally:
        try:
            if df is not None:                # in case upload failed
                # prepare report details
                ag_pg_results = []
                for rec in df.to_dict(orient="records"):
                    gstin = rec["gstin"]
                    ag_stat = get_status(driver, gstin)
                    pg_stat = pg_status(gstin)

                    expected = (
                        "error verifying" if pg_stat == "EXCEPTION" else
                        "valid"           if pg_stat == "ACTIVE"    else
                        "wrong credential" if pg_stat == "INVALID" and get_username(driver, gstin)
                        else "not available" if pg_stat == "INVALID"
                        else "pending"
                    )

                    ag_pg_results.append((gstin, ag_stat, expected))

                edit_success = (get_username(driver, EDIT_GSTIN) == NEW_USERNAME)

                summary = prepare_report(
                    portal=portal_name,
                    workspace=WORKSPACE_NAME,
                    creds_type="GST",
                    ag_pg_results=ag_pg_results,
                    edit_result=edit_success
                )

                insert_into_mongo(summary)    # will no‑op if MONGO_URI unset
                write_json_summary(summary)   # always have a local copy

        finally:
            # delete_from_pg(CSV_PATH)
            driver.quit()            
    


if __name__ == "__main__":
    main()