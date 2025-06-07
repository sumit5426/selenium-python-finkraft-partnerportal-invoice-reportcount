# Automated Invoice Report Verification via Finkraft Portals

## Overview

This script automates the process of downloading and verifying bulk invoice reports from Finkraft partner portals. It logs into multiple portals, triggers invoice report generation, captures the report ID, fetches report status from MongoDB, downloads the invoice ZIP, extracts it, and verifies the invoice count.

---

## Features

* Login automation for multiple partner portals
* Workspace selection
* Invoice report generation
* Report ID capture from network logs
* MongoDB verification of report status
* ZIP file download & extraction
* Invoice count comparison
* Console output summary

---

## Requirements

Install the following Python packages:

```bash
pip install selenium selenium-wire pymongo jinja2
```

---

## Configuration

Update the following credentials in the script:

```python
email_id = "****@kgrp.in"
password = "*****"
```

Set the portals to test:

```python
portals = [
    {"uri": "https://myyatra.finkraft.ai/auth/signin", "workspace_name": "Reserve bank of india yatra"},
    {"uri": "https://mmt.finkraft.ai/auth/signin", "workspace_name": "Mankind pharma"},
]
```

---

## MongoDB Connection

```python
client = MongoClient("mongodb://localhost:27017/")
mongo_db = client["your_database_name"]
mongo_collection = mongo_db["your_collection_name"]
```

---

## Script Structure

### 1. `initialize_driver(download_dir)`

Initializes Chrome WebDriver with custom download directory.

### 2. `login_and_select_workspace(driver, uri, workspace_name)`

Logs into the portal and selects the specified workspace.

### 3. `capture_report_id(driver)`

Monitors browser network traffic to capture `reportId`.

### 4. `wait_for_report_completion(collection, report_id)`

Polls MongoDB for report status and metadata.

### 5. `download_and_verify_invoices(...)`

Downloads and extracts ZIP, compares invoice count with DB.

---

## Execution Flow

```python
for portal in portals:
    driver = initialize_driver(download_dir)
    ui_alert_flag, portal_name = login_and_select_workspace(driver, portal["uri"], portal["workspace_name"])
    report_id = capture_report_id(driver)
    report_info = wait_for_report_completion(mongo_collection, report_id)
    download_and_verify_invoices(driver, **report_info, partner_portal_name=portal_name, workspace_name=portal["workspace_name"], ui_alert_shown_flag=ui_alert_flag, db=mongo_db, download_dir=download_dir)
```

---

## Output

* Portal and workspace info
* UI download alert status
* MongoDB report summary
* Download verification results
* Time taken per invoice
* Cleanup confirmation

---

## Suggestions

* Store credentials securely using environment variables or `.env`
* Convert to class-based structure for modularity
* Add unit tests
* Export results to Excel or Test Management Tools

---

## License

This script is provided for internal automation and testing use only. Handle credentials and data securely.

---

## Author

**Sumit**

---

For enhancements, contact the QA Automation Team.
