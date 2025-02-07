# -*- coding: utf-8 -*-
"""Optimized scraper with performance improvements and formatting fixes."""

import os
import re
import time
import logging
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
REQUEST_TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Formatting constants
HEADER_BG_COLOR = {'red': 0.12, 'green': 0.24, 'blue': 0.35}
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
    """Create optimized HTTP client with retries."""
    if use_cloudscraper:
        return cloudscraper.create_scraper()
    
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    session.mount('https://', HTTPAdapter(max_retries=retry))
    session.headers.update({'User-Agent': USER_AGENT})
    return session

def scrape_mamedica_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float]]:
    """Mamedica scraper with error handling."""
    client = create_http_client(use_cloudscraper)
    try:
        response = client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        products = set()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for option in soup.find_all('option'):
            if 'value' in option.attrs and '|' in option['value']:
                product_name, price_str = option['value'].split('|', 1)
                products.add((
                    product_name.strip(),
                    round(float(price_str.strip()), 2)
                ))

        return sorted(products, key=lambda x: x[0])
    
    except requests.exceptions.Timeout:
        logging.error("Mamedica request timed out")
        return []
    except Exception as error:
        logging.error("Mamedica error: %s", error)
        return []

def scrape_montu_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float, str, str, str]]:
    """Optimized Montu scraper with cloudflare bypass."""
    client = create_http_client(use_cloudscraper)
    try:
        start_time = time.monotonic()
        response = client.get(f"{url}?limit=250", timeout=15)
        response.raise_for_status()
        data = response.json()
        
        products = []
        cannabinoid_pattern = re.compile(r'(THC|CBD)[\s:]*([\d.]+)%', re.IGNORECASE)
        
        for product in data.get('products', []):
            if not product.get('variants'):
                continue
            
            variant = product['variants'][0]
            matches = cannabinoid_pattern.findall(product.get('body_html', ''))
            cannabinoids = {m[0].lower(): f"{m[1]}%" for m in matches}
            
            products.append((
                product.get('title', '').strip(),
                float(variant.get('price', '0').replace('£', '').replace(',', '')),
                cannabinoids.get('thc', 'N/A'),
                cannabinoids.get('cbd', 'N/A'),
                AvailabilityStatus.AVAILABLE.value if variant.get('available') 
                else AvailabilityStatus.NOT_AVAILABLE.value
            ))
        
        products.sort(key=lambda x: (x[4] == AvailabilityStatus.NOT_AVAILABLE.value, x[0]))
        logging.info(f"Montu: Processed {len(products)} products in {time.monotonic()-start_time:.2f}s")
        return products
    
    except Exception as error:
        logging.error("Montu error: %s", error)
        return []

def update_google_sheet(credentials: Credentials, config: DispensaryConfig, products: List[Tuple]):
    """Optimized Google Sheets update with full formatting."""
    try:
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(config.spreadsheet_id)
        worksheet = _get_or_create_worksheet(spreadsheet, config.sheet_name)

        # Fetch existing conditional format rules
        spreadsheet_data = spreadsheet.fetch_sheet_metadata()
        sheet_info = next(
            (s for s in spreadsheet_data['sheets'] if s['properties']['sheetId'] == worksheet.id),
            None
        )
        existing_rules = sheet_info.get('conditionalFormats', []) if sheet_info else []

        # Generate delete requests for existing conditional format rules
        delete_requests = [
            {
                "deleteConditionalFormatRule": {
                    "sheetId": worksheet.id,
                    "index": index
                }
            }
            for index in reversed(range(len(existing_rules)))
        ]

        # Prepare data and timestamp
        data = [config.column_headers] + [list(p) for p in products]
        timestamp_row = len(data) + 2
        timestamp = [[datetime.now().strftime("Updated: %H:%M %d/%m/%Y")]]
        data += [[]] * 2  # Add empty rows for timestamp placement
        data.append(timestamp[0])

        # Clear content and update data
        worksheet.batch_clear(["A:Z"])
        worksheet.update(data, 'A1')

        row_count = len(products)
        col_count = len(config.column_headers)

        # Prepare formatting requests
        format_requests = delete_requests + [
            _create_header_format(worksheet),
            *_create_column_widths(config, worksheet),
            *_create_currency_formats(config, worksheet, row_count),
            *_create_availability_rules(config, worksheet, row_count),
            _create_optimized_borders(worksheet, row_count, col_count),
            _create_frozen_header(worksheet),
            _create_timestamp_format(worksheet, timestamp_row),
            *_create_text_alignment(worksheet, row_count, config)
        ]

        # Execute batch update
        valid_requests = [r for r in format_requests if r]
        if valid_requests:
            worksheet.spreadsheet.batch_update({'requests': valid_requests})

        logging.info(f"{config.name} sheet updated successfully")

    except Exception as error:
        logging.error("Sheet update failed: %s", error)

def _get_or_create_worksheet(spreadsheet, sheet_name: str):
    """Worksheet management with error handling."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(sheet_name, 100, 20)

# Formatting functions --------------------------------------------------------
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
                    'horizontalAlignment': 'CENTER',
                    'wrapStrategy': 'WRAP'
                }
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)'
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

def _create_availability_rules(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    if config.availability_column is None:
        return []
    
    col_index = config.availability_column
    return [{
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{
                    'sheetId': worksheet.id,
                    'startRowIndex': 1,
                    'endRowIndex': row_count + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': len(config.column_headers)
                }],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{"userEnteredValue": f'=${chr(65+col_index)}2="Not Available"'}]
                    },
                    'format': {
                        'backgroundColor': UNAVAILABLE_COLOR,
                        'textFormat': {'bold': True, 'foregroundColor': {'red': 0.4, 'green': 0, 'blue': 0}}
                    }
                }
            }
        }
    }, {
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{
                    'sheetId': worksheet.id,
                    'startRowIndex': 1,
                    'endRowIndex': row_count + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': len(config.column_headers)
                }],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{"userEnteredValue": f'=${chr(65+col_index)}2="Available"'}]
                    },
                    'format': {
                        'backgroundColor': AVAILABLE_COLOR,
                        'textFormat': {'bold': True, 'foregroundColor': {'red': 0, 'green': 0.4, 'blue': 0}}
                    }
                }
            }
        }
    }]

def _create_optimized_borders(worksheet, row_count: int, col_count: int) -> dict:
    """Simplified border application (outer borders only)."""
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
            'innerHorizontal': {'style': 'NONE'},
            'innerVertical': {'style': 'NONE'}
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

def _create_text_alignment(worksheet, row_count: int, config: DispensaryConfig) -> List[dict]:
    """Set column-specific alignment."""
    alignments = {
        0: 'LEFT',    # Product name
        1: 'RIGHT',   # Price
        2: 'CENTER',  # THC %
        3: 'CENTER',  # CBD %
        4: 'CENTER'   # Availability
    }
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
                    'horizontalAlignment': alignment,
                    'wrapStrategy': 'WRAP' if col == 0 else 'OVERFLOW_CELL'
                }
            },
            'fields': 'userEnteredFormat(horizontalAlignment,wrapStrategy)'
        }
    } for col, alignment in alignments.items()]

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
                    },
                    'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}
                }
            },
            'fields': 'userEnteredFormat(textFormat,backgroundColor)'
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
            column_widths={0: 380, 1: 100},
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
            column_widths={0: 280, 1: 100, 2: 80, 3: 80, 4: 120},
            currency_columns=[1],
            availability_column=4,
            use_cloudscraper=True
        )
    ]

    for dispensary in dispensaries:
        start_time = time.monotonic()
        logging.info(f"Starting {dispensary.name}")
        
        try:
            data = dispensary.scrape_method(dispensary.url, dispensary.use_cloudscraper)
            if data:
                update_start = time.monotonic()
                update_google_sheet(credentials, dispensary, data)
                logging.info(f"Updated {dispensary.name} in {time.monotonic() - update_start:.2f}s")
        except Exception as e:
            logging.error(f"Error processing {dispensary.name}: {str(e)}")
        
        logging.info(f"Total {dispensary.name} time: {time.monotonic() - start_time:.2f}s")

if __name__ == "__main__":
    main()
