# -*- coding: utf-8 -*-
"""Modular web scraper for UK medical cannabis dispensaries with Google Sheets integration."""

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
    """Load Google Sheets API credentials with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            return Credentials.from_service_account_file(
                os.environ.get(
                    'GOOGLE_CREDENTIALS_PATH',
                    os.path.join(os.path.dirname(__file__), 'credentials.json')
                ),
                scopes=GOOGLE_SCOPES
            )
        except Exception as error:
            if attempt == MAX_RETRIES - 1:
                logging.error("Failed to load credentials after %d attempts: %s",
                              MAX_RETRIES, error)
                return None
            time.sleep(RETRY_DELAY)

def create_http_client(use_cloudscraper: bool = True) -> requests.Session:
    """Create a configured HTTP client; use cloudscraper if flagged."""
    if use_cloudscraper:
        client = cloudscraper.create_scraper()
    else:
        client = requests.Session()
        retry_policy = Retry(
            total=5,
            backoff_factor=0.8,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=['GET'],
            respect_retry_after_header=True
        )
        client.mount('https://', HTTPAdapter(max_retries=retry_policy))
        client.headers.update({'User-Agent': USER_AGENT})
    return client

def scrape_mamedica_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float]]:
    """Scrape product data from Mamedica's prescription page."""
    try:
        client = create_http_client(use_cloudscraper)
        time.sleep(random.uniform(1.5, 3.5))
        response = client.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        if "repeat-prescription" not in response.text.lower():
            logging.warning("Mamedica page structure validation failed")
            return []

        return sorted(
            {
                (product_name.strip(), round(float(price_str.strip()), 2))
                for option in BeautifulSoup(response.text, 'html.parser').find_all('option')
                if (values := option.get('value', '').split('|', 1)) and len(values) == 2
                and (product_name := values[0]) and (price_str := values[1])
            },
            key=lambda x: x[0]
        )
    except requests.exceptions.RequestException as error:
        logging.error("Mamedica network error: %s", error)
        return []
    except Exception as error:
        logging.error("Unexpected Mamedica error: %s", error)
        return []

def scrape_montu_products(url: str, use_cloudscraper: bool = True) -> List[Tuple[str, float, str, str, str]]:
    """Single-request Montu scraper using limit=250 parameter."""
    client = create_http_client(use_cloudscraper)
    products = []
    
    thc_pattern = re.compile(r'THC[\s:]*([\d.]+)%', re.IGNORECASE)
    cbd_pattern = re.compile(r'CBD[\s:]*([\d.]+)%', re.IGNORECASE)

    try:
        # Single request with max limit
        start_time = time.time()
        response = client.get(
            f"{url}?limit=250",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # Process products
        for product in data.get('products', []):
            if not product.get('variants'):
                continue
            variant = product['variants'][0]
            try:
                products.append((
                    product.get('title', '').strip(),
                    _parse_currency(variant.get('price', '0')),
                    _parse_cannabinoid(product.get('body_html', ''), thc_pattern),
                    _parse_cannabinoid(product.get('body_html', ''), cbd_pattern),
                    AvailabilityStatus.AVAILABLE.value if variant.get('available')
                    else AvailabilityStatus.NOT_AVAILABLE.value
                ))
            except (KeyError, ValueError) as error:
                logging.warning("Montu product parsing error: %s", error)

        logging.info(f"Montu fetched {len(products)} products in {time.time()-start_time:.2f}s")

    except Exception as error:
        logging.error(f"Montu request failed: {error}")

    return sorted(products, key=lambda x: (x[4] == AvailabilityStatus.NOT_AVAILABLE.value, x[0]))

def _parse_currency(price_str: str) -> float:
    """Safely convert currency string to float."""
    try:
        return float(re.sub(r'[^\d.]', '', price_str))
    except (ValueError, TypeError):
        return 0.0

def _parse_cannabinoid(html: str, pattern: re.Pattern) -> str:
    """Extract cannabinoid percentage(s) if available."""
    match = pattern.search(html)
    return f"{match.group(1)}%" if match else "N/A"

def update_google_sheet(credentials: Credentials, config: DispensaryConfig, products: List[Tuple]):
    """Update Google Sheet with data and formatting."""
    try:
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(config.spreadsheet_id)
        worksheet = _get_or_create_worksheet(spreadsheet, config.sheet_name)

        # Prepare update data with numeric values preserved
        validated_data = [config.column_headers] + [list(product) for product in products]
        _update_worksheet_data(worksheet, validated_data)
        _apply_sheet_formatting(worksheet, config, len(products))
        logging.info("Successfully updated %s with %d products", config.name, len(products))
    except gspread.exceptions.APIError as error:
        logging.error("Sheets API error: %s", error.response.text)
    except Exception as error:
        logging.error("Sheet update failed for %s: %s", config.name, error)

def _get_or_create_worksheet(spreadsheet, sheet_name: str):
    """Get existing worksheet or create new if it does not exist."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(sheet_name, rows=100, cols=20)

def _update_worksheet_data(worksheet, data: List[List]):
    """Update worksheet data with batch operations."""
    worksheet.clear()
    if data:
        worksheet.update(data, 'A1')
    worksheet.update_cell(len(data) + 2, 1, datetime.now().strftime("Updated: %H:%M %d/%m/%Y"))

def _apply_sheet_formatting(worksheet, config: DispensaryConfig, product_count: int):
    """Apply all formatting rules to the worksheet."""
    requests_body = [
        _create_header_format(worksheet),
        *_create_column_width_formats(worksheet, config),
        _create_data_borders(worksheet, product_count, len(config.column_headers)),
        _create_currency_formats(worksheet, config, product_count),
        _create_row_color_rule(worksheet, product_count, len(config.column_headers)),
        *_create_availability_rules(worksheet, config, product_count),
        _create_timestamp_format(worksheet, product_count),
        _create_frozen_header_request(worksheet)
    ]
    worksheet.spreadsheet.batch_update({'requests': [r for r in requests_body if r]})

def _create_header_format(worksheet) -> dict:
    """Generate header formatting request."""
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
                    'borders': {
                        'top': {'style': 'SOLID', 'width': 2},
                        'bottom': {'style': 'SOLID', 'width': 2}
                    }
                }
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,borders)'
        }
    }

def _create_column_width_formats(worksheet, config: DispensaryConfig) -> List[dict]:
    """Generate column width adjustment requests."""
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

def _create_data_borders(worksheet, row_count: int, col_count: int) -> dict:
    """Create border formatting for data range."""
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

def _create_currency_formats(worksheet, config: DispensaryConfig, row_count: int) -> List[dict]:
    """Generate currency formatting requests."""
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
                        'pattern': '[$£-809]#,##0.00'
                    },
                    'horizontalAlignment': 'RIGHT'
                }
            },
            'fields': 'userEnteredFormat(numberFormat,horizontalAlignment)'
        }
    } for col in config.currency_columns]

def _create_row_color_rule(worksheet, row_count: int, col_count: int) -> dict:
    """Create alternating row color rule."""
    return {
        'addConditionalFormatRule': {
            'rule': {
                'ranges': [{
                    'sheetId': worksheet.id,
                    'startRowIndex': 1,
                    'endRowIndex': row_count + 1,
                    'startColumnIndex': 0,
                    'endColumnIndex': col_count
                }],
                'booleanRule': {
                    'condition': {
                        'type': 'CUSTOM_FORMULA',
                        'values': [{"userEnteredValue": "=ISEVEN(ROW())"}]
                    },
                    'format': {'backgroundColor': ALTERNATING_ROW_COLOR}
                }
            }
        }
    }

def _create_availability_rules(worksheet, config: DispensaryConfig, row_count: int) -> List[dict]:
    """Generate availability formatting rules."""
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
    return [
        {
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': [range_def],
                    'booleanRule': {
                        'condition': {
                            'type': 'TEXT_EQ',
                            'values': [{'userEnteredValue': AvailabilityStatus.NOT_AVAILABLE.value}]
                        },
                        'format': {
                            'backgroundColor': UNAVAILABLE_COLOR,
                            'textFormat': {'bold': True}
                        }
                    }
                }
            }
        },
        {
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': [range_def],
                    'booleanRule': {
                        'condition': {
                            'type': 'TEXT_EQ',
                            'values': [{'userEnteredValue': AvailabilityStatus.AVAILABLE.value}]
                        },
                        'format': {
                            'backgroundColor': AVAILABLE_COLOR,
                            'textFormat': {'bold': True}
                        }
                    }
                }
            }
        }
    ]

def _create_timestamp_format(worksheet, row_count: int) -> dict:
    """Create timestamp formatting request."""
    return {
        'repeatCell': {
            'range': {
                'sheetId': worksheet.id,
                'startRowIndex': row_count + 2,
                'endRowIndex': row_count + 3,
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

def _create_frozen_header_request(worksheet) -> dict:
    """Create request to freeze header row."""
    return {
        'updateSheetProperties': {
            'properties': {
                'sheetId': worksheet.id,
                'gridProperties': {'frozenRowCount': 1}
            },
            'fields': 'gridProperties.frozenRowCount'
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
            logging.info(f"Processing {dispensary.name}")
            start_time = time.time()
            if data := dispensary.scrape_method(dispensary.url, dispensary.use_cloudscraper):
                update_google_sheet(credentials, dispensary, data)
                logging.info(f"Completed {dispensary.name} in {time.time() - start_time:.2f}s")
            else:
                logging.warning(f"No data retrieved for {dispensary.name}")
        except Exception as e:
            logging.error(f"Fatal error processing {dispensary.name}: {str(e)}")
            continue

if __name__ == "__main__":
    main()
