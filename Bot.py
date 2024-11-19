# -*- coding: utf-8 -*-
import os
import requests
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
from bs4 import BeautifulSoup
import re

# Constants
CREDENTIALS_FILE_NAME = 'credentials.json'

class Dispensary:
    def __init__(self, name, url, spreadsheet_id, sheet_name, scrape_method, columns):
        self.name = name
        self.url = url
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.scrape_method = scrape_method
        self.columns = columns

    def scrape_data(self):
        return self.scrape_method(self.url)

def load_credentials():
    """Load the Google Sheets API credentials."""
    return Credentials.from_service_account_file(CREDENTIALS_FILE_NAME, scopes=["https://www.googleapis.com/auth/spreadsheets"])

def scrape_mamedica(url):
    """Fetch the HTML content and extract product data from Mamedica."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    unique_products = sorted({
        (product_name.strip(), round(float(price.strip()), 2))
        for option in soup.find_all('option')
        if (value := option.get('value')) and '|' in value
        if (product_name := value.split('|')[0]) and (price := value.split('|')[1])
    }, key=lambda x: x[0])  # Sort by product name

    return unique_products

def scrape_montu(url):
    """Fetch the JSON content from Montu and extract product data."""
    all_products = []
    page = 1

    while (products := requests.get(f"{url}?page={page}").json().get('products', [])):
        all_products.extend(products)
        page += 1

    unique_products = [
        (product['title'].strip(), round(float(product['variants'][0]['price'].strip()), 2),
         re.search(r'THC\s*([\d.]+%)', product['body_html'], re.IGNORECASE).group(1) if (thc_match := re.search(r'THC\s*([\d.]+%)', product['body_html'], re.IGNORECASE)) else '',
         re.search(r'CBD\s*([\d.]+%)', product['body_html'], re.IGNORECASE).group(1) if (cbd_match := re.search(r'CBD\s*([\d.]+%)', product['body_html'], re.IGNORECASE)) else '',
         'Available Now' if product['variants'][0]['available'] else 'Not Available')
        for product in all_products if product['title'] and product['variants'][0]['price']
    ]

    return sorted(unique_products, key=lambda x: (x[4] == 'Not Available', x[0]))

def prepare_updates(columns, data):
    """Prepare updates and formatting in memory."""
    timestamp = [[datetime.now().strftime("Updated on: %H:%M %d/%m/%Y")]]
    updates = [columns] + data + [[]] + timestamp
    
    row_colors = [(1.0, 1.0, 1.0) if row % 2 == 0 else (0.95, 0.95, 0.95) for row in range(1, len(data) + 3)]
    
    formatting_requests = [
        {
            'repeatCell': {
                'range': {
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': len(columns),
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True}
                    }
                },
                'fields': 'userEnteredFormat.textFormat.bold'
            }
        },
        *[
            {
                'repeatCell': {
                    'range': {
                        'startRowIndex': row_idx,
                        'endRowIndex': row_idx + 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': len(columns),
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': row_colors[row_idx - 1][0],
                                'green': row_colors[row_idx - 1][1],
                                'blue': row_colors[row_idx - 1][2]
                            }
                        }
                    },
                    'fields': 'userEnteredFormat.backgroundColor'
                }
            }
            for row_idx in range(1, len(data) + 3)
        ],
        {
            'repeatCell': {
                'range': {
                    'startRowIndex': len(data) + 2,
                    'endRowIndex': len(data) + 3,
                    'startColumnIndex': 0,
                    'endColumnIndex': len(columns),
                },
                'cell': {
                    'userEnteredFormat': {
                        'textFormat': {'bold': True}
                    }
                },
                'fields': 'userEnteredFormat.textFormat.bold'
            }
        }
    ]
    
    return updates, formatting_requests

def update_google_sheet_with_gspread(creds, spreadsheet_id, sheet_name, data, columns):
    """Update the specified Google Sheet with data and a timestamp."""
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
    worksheet.clear()

    updates, _ = prepare_updates(columns, data)
    worksheet.update(range_name='A1', values=updates)
    print(f"Sheet '{sheet_name}' updated successfully.")

def process_dispensary(creds, dispensary):
    """Process a single dispensary."""
    print(f"Processing dispensary: {dispensary.name}")
    data = dispensary.scrape_data()
    update_google_sheet_with_gspread(
        creds=creds,
        spreadsheet_id=dispensary.spreadsheet_id,
        sheet_name=dispensary.sheet_name,
        data=data,
        columns=dispensary.columns
    )
    print(f"Dispensary '{dispensary.name}' processing complete.")

def main():
    creds = load_credentials()
    if not creds:
        print("No valid credentials found.")
        return

    dispensaries = [
        Dispensary(
            name="Mamedica",
            url="https://mamedica.co.uk/repeat-prescription/",
            spreadsheet_id="1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw",
            sheet_name="Mamedica List",
            scrape_method=scrape_mamedica,
            columns=['Product', 'Price']
        ),
        Dispensary(
            name="Montu",
            url="https://store.montu.uk/products.json",
            spreadsheet_id="1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU",
            sheet_name="Montu List",
            scrape_method=scrape_montu,
            columns=['Product', 'Price', 'THC %', 'CBD %', 'Availability']
        ),
    ]

    for dispensary in dispensaries:
        process_dispensary(creds, dispensary)

if __name__ == "__main__":
    main()
