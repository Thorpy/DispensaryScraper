import csv
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Google Sheets setup
CREDENTIALS_FILE_NAME = os.path.join(os.path.dirname(__file__), 'credentials.json')
DISPENSARIES = [
    {
        'name': 'Mamedica',
        'url': 'https://mamedica.co.uk/repeat-prescription/',
        'spreadsheet_id': '1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw',
        'sheet_name': 'Mamedica List'
    },
    # Add more dispensaries here
    # {
    #     'name': 'Another Dispensary',
    #     'url': 'https://example.com',
    #     'spreadsheet_id': 'your_spreadsheet_id',
    #     'sheet_name': 'Your Sheet Name'
    # }
]

def load_credentials():
    """Load the Google Sheets API credentials."""
    if os.path.exists(CREDENTIALS_FILE_NAME):
        return service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE_NAME,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    return None

def scrape_mamedica():
    """Fetch the HTML content and extract product data from Mamedica."""
    url = DISPENSARIES[0]['url']
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    unique_products = set()
    for option in soup.find_all('option'):
        value = option.get('value')
        if value and '|' in value:
            parts = value.split('|')
            if len(parts) == 2:
                product_name, price = parts
                try:
                    unique_products.add((product_name.strip(), float(price.strip())))
                except ValueError:
                    continue
    return sorted(unique_products, key=lambda x: x[0])  # Sort A-Z by product name

def save_to_csv(data, filename='products.csv'):
    """Save data to CSV with the correct format."""
    with open(filename, mode='w', newline='', encoding='utf-8') as csv_file:
        fieldnames = ['Product', 'Price']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for product, price in data:
            writer.writerow({'Product': product, 'Price': f'£{price:.2f}'})
    print("CSV file has been created with unique products sorted by name.")

def read_csv(file_name):
    """Read the CSV file and return unique products sorted by price."""
    try:
        df = pd.read_csv(file_name)
        unique_products = df.drop_duplicates(subset='Product').sort_values(by='Price')
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
    """Update the Google Sheet with the new data."""
    try:
        requests = [{
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

        batch_update_request = {"requests": requests}
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=batch_update_request).execute()
        print(f"Successfully updated the sheet with {len(data)} rows.")
    except HttpError as error:
        print(f"Error updating sheet: {error}")

def main():
    """Main function to run the script."""
    creds = load_credentials()
    if not creds:
        print("No valid credentials found.")
        return

    service = build('sheets', 'v4', credentials=creds)

    # Scrape data and save to CSV
    data = scrape_mamedica()
    save_to_csv(data)

    # Read the CSV file and prepare data for updating
    data = read_csv('products.csv')
    if data:
        # Retrieve the sheet ID for the Mamedica sheet
        sheet_id = get_sheet_id(service, DISPENSARIES[0]['spreadsheet_id'], DISPENSARIES[0]['sheet_name'])
        update_google_sheet(service, DISPENSARIES[0]['spreadsheet_id'], sheet_id, data)
    else:
        print("No data to update in Google Sheets.")

if __name__ == '__main__':
    main()
