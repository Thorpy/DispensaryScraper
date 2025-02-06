# -*- coding: utf-8 -*-
"""Optimized web scraper with Google Sheets integration."""

import os
import re
import time
import logging
import random
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Callable
from dataclasses import dataclass
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import cloudscraper
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

# Constants -------------------------------------------------------------------
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_RETRIES = 3
RETRY_DELAY = 5
REQUEST_TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Formatting constants
HEADER_BG_COLOR = {'red': 0.12, 'green': 0.24, 'blue': 0.35}
ALTERNATING_ROW_COLOR = {'red': 0.98, 'green': 0.98, 'blue': 0.98}
UNAVAILABLE_COLOR = {'red': 1, 'green': 0.9, 'blue': 0.9}
AVAILABLE_COLOR = {'red': 0.9, 'green': 1, 'blue': 0.9}
TIMESTAMP_COLOR = {'red': 0.5, 'green': 0.5, 'blue': 0.5}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

@dataclass
class DispensaryConfig:
    """Configuration for dispensary scraping and spreadsheet settings."""
    name: str
    url: str
    spreadsheet_id: str
    sheet_name: str
    scrape_method: Callable
    column_headers: List[str]
    column_widths: Dict[int, int]
    currency_columns: List[int] = None
    availability_column: Optional[int] = None
    use_cloudscraper: bool = True

class AvailabilityStatus(Enum):
    AVAILABLE = 'Available'
    NOT_AVAILABLE = 'Not Available'

def load_google_credentials() -> Optional[Credentials]:
    """Load Google Sheets API credentials."""
    try:
        return Credentials.from_service_account_file(
            os.path.join(os.path.dirname(__file__), 'credentials.json'),
            scopes=GOOGLE_SCOPES
        )
    except Exception as error:
        logging.error("Failed to load credentials: %s", error)
        return None

def create_http_client(use_cloudscraper: bool = True) -> requests.Session:
    """Create a configured HTTP client."""
    if use_cloudscraper:
        return cloudscraper.create_scraper()
    
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers.update({'User-Agent': USER_AGENT})
    return session

def scrape_mamedica_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float]]:
    """Scrape Mamedica products."""
    try:
        client = create_http_client(use_cloudscraper)
        response = client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        products = set()
        
        for option in soup.find_all('option'):
            if '|' in option['value']:
                product_name, price_str = option['value'].split('|', 1)
                products.add((
                    product_name.strip(),
                    round(float(price_str.strip()), 2)
                ))

        return sorted(products, key=lambda x: x[0])
    
    except Exception as error:
        logging.error("Mamedica error: %s", error)
        return []

def scrape_montu_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float, str, str, str]]:
    """Optimized Montu scraper with single request."""
    client = create_http_client(use_cloudscraper)
    
    try:
        start_time = time.monotonic()
        response = client.get(f"{url}?limit=250", timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = []
        available_str = AvailabilityStatus.AVAILABLE.value
        not_available_str = AvailabilityStatus.NOT_AVAILABLE.value
        
        for product in data.get('products', []):
            variant = product.get('variants', [{}])[0]
            body_html = product.get('body_html', '')
            
            # Extract cannabinoids
            thc = re.search(r'THC[\s:]*([\d.]+)%', body_html, re.IGNORECASE)
            cbd = re.search(r'CBD[\s:]*([\d.]+)%', body_html, re.IGNORECASE)
            
            products.append((
                product.get('title', '').strip(),
                float(variant.get('price', '0').replace('£', '').replace(',', '')),
                f"{thc.group(1)}%" if thc else 'N/A',
                f"{cbd.group(1)}%" if cbd else 'N/A',
                available_str if variant.get('available') else not_available_str
            ))
        
        # Sort by availability then name
        products.sort(key=lambda x: (x[4] == not_available_str, x[0]))
        
        logging.info(f"Montu: {len(products)} products in {time.monotonic()-start_time:.2f}s")
        return products
    
    except Exception as error:
        logging.error("Montu error: %s", error)
        return []

def update_google_sheet(credentials: Credentials, config: DispensaryConfig, products: List[Tuple]):
    """Update Google Sheet with optimized formatting."""
    try:
        start_time = time.monotonic()
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(config.spreadsheet_id)
        worksheet = _get_or_create_worksheet(spreadsheet, config.sheet_name)

        # Update data
        data = [config.column_headers] + [list(p) for p in products]
        worksheet.clear()
        worksheet.update(data, 'A1')

        # Apply formatting
        format_requests = [
            _create_header_format(worksheet),
            *_create_column_widths(config, worksheet),
            _create_currency_formats(config, worksheet, len(products)),
            _create_availability_formats(config, worksheet, len(products)),
            _create_borders(worksheet, len(products), len(config.column_headers)),
            _create_frozen_header(worksheet),
            _create_timestamp_format(worksheet, len(data) + 2)
        ]
        
        # Filter out None requests and execute
        valid_requests = [r for r in format_requests if r is not None]
        if valid_requests:
            worksheet.spreadsheet.batch_update({'requests': valid_requests})

        logging.info(f"Updated {config.name} in {time.monotonic()-start_time:.2f}s")

    except Exception as error:
        logging.error("Sheet update failed: %s", error)

def _get_or_create_worksheet(spreadsheet, sheet_name: str):
    """Get or create worksheet."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(sheet_name, 100, 20)

# Formatting helper functions -------------------------------------------------
def _create_header_format(worksheet) -> dict:
    return {
        'repeatCell': {
            'range': {'sheetId': worksheet.id, 'startRowIndex': 0, 'endRowIndex': 1},
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': HEADER_BG_COLOR,
                    'textFormat': {
                        'foregroundColor': {'red': 1, 'green': 1, 'blue': 1},
                        'bold': True,
                        'fontSize': 12
                    },
                    'horizontalAlignment': 'CENTER'
                }
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
        }
    }

def _create_column_widths(config: DispensaryConfig, worksheet) -> List[dict]:
    return [{
        'updateDimensionProperties': {
            'range': {
                'sheetId': worksheet.id,
                'dimension': 'COLUMNS',
                'startIndex': col,
                'endIndex': col + 1
            },
            'properties': {'pixelSize': width},
            'fields': 'pixelSize'
        }
    } for col, width in config.column_widths.items()]

def _create_currency_formats(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    if not config.currency_columns:
        return []
    
    return [{
        'repeatCell': {
            'range': {
                'sheetId': worksheet.id,
                'startRowIndex': 1,
                'endRowIndex': row_count + 1,
                'startColumnIndex': col,
                'endColumnIndex': col + 1
            },
            'cell': {
                'userEnteredFormat': {
                    'numberFormat': {
                        'type': 'CURRENCY',
                        'pattern': '£#,##0.00'
                    }
                }
            },
            'fields': 'userEnteredFormat.numberFormat'
        }
    } for col in config.currency_columns]

def _create_availability_formats(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    if config.availability_column is None:
        return []
    
    col = config.availability_column
    range_def = {
        'sheetId': worksheet.id,
        'startRowIndex': 1,
        'endRowIndex': row_count + 1,
        'startColumnIndex': col,
        'endColumnIndex': col + 1
    }
    
    return [{
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [range_def],
                'booleanRule': {
                    'condition': {
                        'type': 'TEXT_EQ',
                        'values': [{'userEnteredValue': status.value}]
                    },
                    'format': {
                        'backgroundColor': color,
                        'textFormat': {'bold': True}
                    }
                }
            }
        }
    } for status, color in [
        (AvailabilityStatus.NOT_AVAILABLE, UNAVAILABLE_COLOR),
        (AvailabilityStatus.AVAILABLE, AVAILABLE_COLOR)
    ]]

def _create_borders(worksheet, row_count: int, col_count: int) -> dict:
    return {
        'updateBorders': {
            'range': {
                'sheetId': worksheet.id,
                'startRowIndex': 0,
                'endRowIndex': row_count + 1,
                'startColumnIndex': 0,
                'endColumnIndex': col_count
            },
            'top': {'style': 'SOLID', 'width': 1},
            'bottom': {'style': 'SOLID', 'width': 1},
            'left': {'style': 'SOLID', 'width': 1},
            'right': {'style': 'SOLID', 'width': 1},
            'innerHorizontal': {'style': 'SOLID', 'width': 1},
            'innerVertical': {'style': 'SOLID', 'width': 1}
        }
    }

def _create_frozen_header(worksheet) -> dict:
    return {
        'updateSheetProperties': {
            'properties': {
                'sheetId': worksheet.id,
                'gridProperties': {'frozenRowCount': 1}
            },
            'fields': 'gridProperties.frozenRowCount'
        }
    }

def _create_timestamp_format(worksheet, row: int) -> dict:
    return {
        'repeatCell': {
            'range': {
                'sheetId': worksheet.id,
                'startRowIndex': row,
                'endRowIndex': row + 1,
                'startColumnIndex': 0,
                'endColumnIndex': 1
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {
                        'italic': True,
                        'fontSize': 10,
                        'foregroundColor': TIMESTAMP_COLOR
                    }
                }
            },
            'fields': 'userEnteredFormat.textFormat'
        }
    }

def main():
    credentials = load_google_credentials()
    if not credentials:
        return

    dispensaries = [
        DispensaryConfig(
            name="Mamedica",
            url="https://mamedica.co.uk/repeat-prescription/",
            spreadsheet_id=os.getenv('MAMEDICA_SHEET_ID', '1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw'),
            sheet_name="Mamedica List",
            scrape_method=scrape_mamedica_products,
            column_headers=['Product', 'Price'],
            column_widths={0: 400, 1: 100},
            currency_columns=[1],
            use_cloudscraper=True
        ),
        DispensaryConfig(
            name="Montu",
            url="https://store.montu.uk/products.json",
            spreadsheet_id=os.getenv('MONTU_SHEET_ID', '1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU'),
            sheet_name="Montu List",
            scrape_method=scrape_montu_products,
            column_headers=['Product', 'Price', 'THC %', 'CBD %', 'Availability'],
            column_widths={0: 220, 1: 100, 2: 80, 3: 80, 4: 120},
            currency_columns=[1],
            availability_column=4,
            use_cloudscraper=True
        )
    ]

    for dispensary in dispensaries:
        try:
            start_time = time.monotonic()
            logging.info(f"Starting {dispensary.name}")
            
            if data := dispensary.scrape_method(dispensary.url, dispensary.use_cloudscraper):
                update_google_sheet(credentials, dispensary, data)
                logging.info(f"Completed {dispensary.name} in {time.monotonic() - start_time:.2f}s")
            
        except Exception as e:
            logging.error(f"Error processing {dispensary.name}: {str(e)}")

if __name__ == "__main__":
    main()
