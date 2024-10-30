# -*- coding: utf-8 -*-
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime

# Google Sheets setup
CREDENTIALS_FILE_NAME = os.path.join(os.path.dirname(__file__), 'credentials.json')

# Define your dispensaries
dispensaries = {
    "Mamedica": {
        "url": "https://mamedica.co.uk/repeat-prescription/",
        "spreadsheet_id": "1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw",
        "sheet_name": "Mamedica List"
    },
    # Add more dispensaries here
}

def load_credentials():
    """Load the Google Sheets API credentials."""
    if os.path.exists(CREDENTIALS_FILE_NAME):
        return service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE_NAME,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    return None

def scrape_dispensary(url):
    """Fetch the HTML content and extract product data from a dispensary."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    unique_products = []
    for option in soup.find_all('option'):
        value = option.get('value')
        if value and '|' in value:
            parts = value.split('|')
            if len(parts) == 2:
                product_name, price = parts
                try:
                    unique_products.append((product_name.strip(), float(price.strip())))
                except ValueError:
                    continue

    return sorted(unique_products, key=lambda x: x[0])  # Sort by product name

def save_to_csv(data, filename):
    """Save data to CSV with the correct format."""
    df = pd.DataFrame(data, columns=['Product', 'Price'])
    df['Price'] = df['Price'].apply(lambda x: f'\u00A3{x:.2f}')  # Format price as currency
    df.to_csv(filename, index=False)
    print(f"CSV file '{filename}' has been created with unique products sorted by name.")

def read_csv(file_name):
    """Read the CSV file and return unique products sorted by product name."""
    try:
        df = pd.read_csv(file_name)
        unique_products = df.drop_duplicates(subset='Product').sort_values(by='Product')
        return unique_products[['Product', 'Price']].values.tolist()
    except KeyError as e:
        print(f"Error: Missing expected column in CSV file - {e}")
        return []

def get_sheet_id(service, spreadsheet_id, sheet_name):
    """Retrieve the sheet ID based on the sheet name."""
    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', [])
        for sheet in sheets:
            if sheet['properties']['title'] == sheet_name:
                return sheet['properties']['sheetId']
        print(f"Sheet with name '{sheet_name}' not found.")
    except HttpError as error:
        print(f"Error retrieving sheet ID: {error}")
    return None

def update_google_sheet(service, spreadsheet_id, sheet_id, data):
    """Update the Google Sheet with new data and a static timestamp, clearing any old data first."""
    try:
        # Clear existing product data
        clear_data_request = {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,  # Arbitrary large number to clear all rows that may contain data
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "fields": "userEnteredValue",
            }
        }

        # Prepare data update request
        data_requests = [{
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(data) + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "rows": [{"values": [{"userEnteredValue": {"stringValue": str(cell)}} for cell in row]} for row in data],
                "fields": "userEnteredValue",
            }
        }]

        # Create a new timestamp
        timestamp = datetime.now().strftime("Updated on: %H:%M %d/%m/%Y")

        # Timestamp request two rows below the data
        timestamp_request = {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": len(data) + 2,
                    "endRowIndex": len(data) + 3,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rows": [{
                    "values": [{"userEnteredValue": {"stringValue": timestamp}}]
                }],
                "fields": "userEnteredValue",
            }
        }

        # Execute batch update with clear and data requests
        batch_update_request = {"requests": [clear_data_request] + data_requests + [timestamp_request]}
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=batch_update_request).execute()
        print(f"Successfully updated the sheet with {len(data)} rows and added the timestamp: {timestamp}")

    except HttpError as error:
        print(f"Error updating sheet: {error}")

def main():
    """Main function to run the script for all dispensaries."""
    creds = load_credentials()
    if not creds:
        print("No valid credentials found.")
        return

    service = build('sheets', 'v4', credentials=creds)

    for dispensary, details in dispensaries.items():
        print(f"Processing {dispensary}...")
        data = scrape_dispensary(details["url"])
        csv_file_name = f"{dispensary.lower().replace(' ', '_')}_products.csv"
        save_to_csv(data, csv_file_name)

        # Read the CSV file and prepare data for updating
        data = read_csv(csv_file_name)
        if data:
            sheet_id = get_sheet_id(service, details["spreadsheet_id"], details["sheet_name"])
            update_google_sheet(service, details["spreadsheet_id"], sheet_id, data)
        else:
            print(f"No data to update for {dispensary}.")

if __name__ == '__main__':
    main()
