# -*- coding: utf-8 -*-
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
import gspread
from datetime import datetime
import re

# Constants
CREDENTIALS_FILE_NAME = os.path.join(os.path.dirname(__file__), 'credentials.json')

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
    if os.path.exists(CREDENTIALS_FILE_NAME):
        return Credentials.from_service_account_file(CREDENTIALS_FILE_NAME, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    print("Credentials file not found.")
    return None

def scrape_mamedica(url):
    """Fetch the HTML content and extract product data from Mamedica."""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    unique_products = set(
        (product_name.strip(), round(float(price.strip()), 2))
        for option in soup.find_all('option')
        if (value := option.get('value')) and '|' in value
        if (parts := value.split('|')) and len(parts) == 2
        if (product_name := parts[0]) and (price := parts[1])
    )
    
    return sorted(unique_products, key=lambda x: x[0])  # Sort by product name

def scrape_montu(url):
    """Fetch the JSON content from Montu and extract product data."""
    page = 1
    all_products = []

    while True:
        response = requests.get(f"{url}?page={page}")
        products = response.json().get('products', [])
        if not products:
            break  # Stop if there are no more products
        all_products.extend(products)
        page += 1

    unique_products = []
    for product in all_products:
        title = product.get('title')
        price = product.get('variants', [{}])[0].get('price')
        available = product.get('variants', [{}])[0].get('available', False)
        
        # Extract THC and CBD content from body_html
        body_html = product.get('body_html', '')
        thc_content = ''
        cbd_content = ''
        if body_html:
            thc_match = re.search(r'THC\s*([\d.]+%)', body_html, re.IGNORECASE)
            cbd_match = re.search(r'CBD\s*([\d.]+%)', body_html, re.IGNORECASE)
            if not thc_match:
                thc_match = re.search(r'([\d.]+%)\s*THC', body_html, re.IGNORECASE)
            if not cbd_match:
                cbd_match = re.search(r'([\d.]+%)\s*CBD', body_html, re.IGNORECASE)
            if thc_match:
                thc_content = thc_match.group(1)
            if cbd_match:
                cbd_content = cbd_match.group(1)

        available_status = 'Available Now' if available else 'Not Available'

        if title and price:
            unique_products.append((title.strip(), round(float(price.strip()), 2), thc_content, cbd_content, available_status))

    # Filter out any rows that are entirely blank
    unique_products = [row for row in unique_products if any(row)]

    # Sort by product name and availability
    available_products = sorted([p for p in unique_products if p[4] == 'Available Now'], key=lambda x: x[0])
    unavailable_products = sorted([p for p in unique_products if p[4] == 'Not Available'], key=lambda x: x[0])

    return available_products + unavailable_products

def update_google_sheet_with_gspread(spreadsheet_id, sheet_name, data, columns):
    """Update the specified Google Sheet with data and a timestamp."""
    creds = load_credentials()
    if creds is None:
        print("No valid credentials found.")
        return
    gc = gspread.authorize(creds)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
    worksheet.clear()
    worksheet.append_row(columns)
    
    data_to_update = [columns] + data
    cell_list = worksheet.range(f'A1:{chr(64 + len(columns))}{len(data_to_update)}')
    for cell, value in zip(cell_list, [item for sublist in data_to_update for item in sublist]):
        cell.value = value

    worksheet.update_cells(cell_list)
    apply_formatting(worksheet, columns)
    timestamp = datetime.now().strftime("Updated on: %H:%M %d/%m/%Y")
    worksheet.update(range_name=f'A{len(data) + 3}', values=[[timestamp]])
    worksheet.format(f'A{len(data) + 3}', {'textFormat': {'bold': True}})
    print(f"Sheet '{sheet_name}' updated successfully.")

def apply_formatting(worksheet, columns):
    """Apply formatting to the Google Sheet."""
    worksheet.format('A1:Z1', {'textFormat': {'bold': True}})
    worksheet.freeze(rows=1)
    for i, column in enumerate(columns, start=1):
        if column == 'Price':
            worksheet.format(f'{chr(64 + i)}2:{chr(64 + i)}', {'numberFormat': {'type': 'CURRENCY', 'pattern': '\u00A3#,##0.00'}})

def process_dispensary(dispensary):
    """Process a single dispensary."""
    print(f"Processing dispensary: {dispensary.name}")
    data = dispensary.scrape_data()
    update_google_sheet_with_gspread(dispensary.spreadsheet_id, dispensary.sheet_name, data, dispensary.columns)
    print(f"Dispensary '{dispensary.name}' processing complete.")

def main():
    creds = load_credentials()
    if not creds:
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
            columns=['Product', 'Price', 'THC Content', 'CBD Content', 'Availability']
        ),
        # Add more dispensaries here...
    ]

    for dispensary in dispensaries:
        process_dispensary(dispensary)

if __name__ == "__main__":
    main()
