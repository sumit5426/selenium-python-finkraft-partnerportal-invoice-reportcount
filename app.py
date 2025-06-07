import os

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
import pandas as pd
from io import StringIO
from datetime import datetime
import subprocess
from fastapi.responses import JSONResponse
import base64
import re
app = FastAPI()
load_dotenv()
mongo_db_username = os.environ.get("MONGO_DB_USERNAME")
mongo_db_password = os.environ.get("MONGO_DB_PASSWORD")

# Allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Connect to MongoDB
connection_string = (f"mongodb://{mongo_db_username}:{mongo_db_password}"
                             "@mongodb.centralindia.cloudapp.azure.com/admin?"
                             "directConnection=true&serverSelectionTimeoutMS=5000&appName=mongosh+2.2.3")
client = MongoClient(connection_string)
db = client['gstservice']
collection = db["selenium-summary-report"]
@app.get("/data")
def get_data():
    data = list(collection.find({}, {"_id": 0}))  # Exclude _id if you don't need it
    print(data)
    return data
@app.get("/export_today_data")
def export_today_data():
    print("Export todays data")
    today_date = datetime.now().strftime("%Y-%m-%d")
    print("Today", today_date)
    data = list(collection.find({"invoice_initialization_date_time": today_date}, {"_id": 0}))
    print("Data" , data)
    return data

@app.get("/export_today_csv")
def export_today_data():
    # Format today's date in 'YYYY-MM-DD'
    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Today's date: {today_date}")
    # Query MongoDB for data with 'created_at' matching today's date
    data = list(collection.find({"created_at": today_date}, {"_id": 0}))
    print(f"Today's data: {data}")
    if not data:
        return Response(content="No data found for today.", media_type="text/plain", status_code=404)
    # Convert the data to CSV using pandas
    df = pd.DataFrame(data)
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_content = csv_buffer.getvalue()
    return Response(content=csv_content, media_type="text/csv")