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

def check_on_airlines():        
            
    print("Checking on association of PAN for all 5 airlines")

def main():
    driver = init_driver()
    login_and_pick_workspace(driver)
    upload_csv(driver, CSV_PATH)
    print("DOne")
    driver.quit()

if __name__ == "__main__"  :
    main()