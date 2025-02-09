# -*- coding: utf-8 -*-
"""Optimized cannabis dispensary price scraper with Google Sheets integration."""

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

# ============================= CONFIGURATION ==============================
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

DISPENSARIES = [
    DispensaryConfig(
        name="Mamedica",
        url="https://mamedica.co.uk/repeat-prescription/",
        spreadsheet_id=os.getenv('MAMEDICA_SHEET_ID', '1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw'),
        sheet_name="Mamedica List",
        scrape_method=lambda url, _: scrape_mamedica_products(url),
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
        scrape_method=lambda url, _: scrape_montu_products(url),
        column_headers=['Product', 'Price', 'THC %', 'CBD %', 'Availability'],
        column_widths={0: 280, 1: 100, 2: 80, 3: 80, 4: 120},
        currency_columns=[1],
        availability_column=4,
        use_cloudscraper=True
    )
]

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
REQUEST_TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Formatting constants
HEADER_BG_COLOR = {'red': 0.12, 'green': 0.24, 'blue': 0.35}
WHITE = {'red': 1, 'green': 1, 'blue': 1}
LIGHT_GREEN = {'red': 0.85, 'green': 0.95, 'blue': 0.85}  # Light green
DARK_GREEN = {'red': 0.7, 'green': 0.9, 'blue': 0.7}      # Medium green
LIGHT_RED = {'red': 1, 'green': 0.9, 'blue': 0.9}         # Light red
DARK_RED = {'red': 1, 'green': 0.7, 'blue': 0.7}          # Medium red
ALTERNATING_ROW_COLOR = {'red': 0.97, 'green': 0.97, 'blue': 0.97}  # Light grey
AVAILABLE_TEXT_COLOR = {'red': 0, 'green': 0.4, 'blue': 0}          # Dark green text
UNAVAILABLE_TEXT_COLOR = {'red': 0.6, 'green': 0, 'blue': 0}        # Dark red text
WHITE_TEXT = {'red': 1, 'green': 1, 'blue': 1}                      # White text
TIMESTAMP_COLOR = {'red': 0.5, 'green': 0.5, 'blue': 0.5}

# ============================ CORE FUNCTIONALITY ==========================
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
    """Scrape products from Mamedica website."""
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
    """Scrape products from Montu/Australis website."""
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

def update_google_sheet(config, worksheet, delete_requests, row_count, timestamp_row):
    try:
        col_count = len(config.column_headers)

        # update_google_sheet() to pass config to zebra stripes:
        format_requests = delete_requests + [
            _create_header_format(worksheet),
            *_create_column_widths(config, worksheet),
            *_create_currency_formats(config, worksheet, row_count),
            _create_zebra_stripes(config, worksheet, row_count, col_count),  # Now takes config
            *_create_availability_rules(config, worksheet, row_count),
            _create_optimized_borders(worksheet, row_count, col_count),
            _create_frozen_header(worksheet),
            _create_timestamp_format(worksheet, timestamp_row),
            *_create_text_alignment(worksheet, row_count, config)
        ]

        # Execute batch update
        if valid_requests := [r for r in format_requests if r]:
            worksheet.spreadsheet.batch_update({'requests': valid_requests})

        logging.info(f"{config.name} sheet updated successfully")

    except Exception as error:
        logging.error("Sheet update failed: %s", error)

# ============================ HELPER FUNCTIONS ============================
def _get_or_create_worksheet(spreadsheet, sheet_name: str):
    """Manage worksheet creation/retrieval."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(sheet_name, 100, 20)

def _create_header_format(worksheet) -> dict:
    """Create header row formatting."""
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
    """Set column widths."""
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
    """Apply currency formatting."""
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
                    'numberFormat': {'type': 'CURRENCY', 'pattern': '£#,##0.00'}
                }
            },
            'fields': 'userEnteredFormat.numberFormat'
        }
    } for col in config.currency_columns]

def _create_zebra_stripes(config, worksheet, row_count: int, col_count: int) -> dict:
    """Create alternating row colors for dispensaries without availability column."""
    if config.availability_column is not None:
        return None  # Handled by availability rules
    
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
                    'format': {
                        'backgroundColor': ALTERNATING_ROW_COLOR,
                        'textFormat': {'foregroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2}}
                    }
                }
            }
        }
    }

def _create_availability_rules(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    """Create advanced availability formatting with alternating shades."""
    if config.availability_column is None:
        return []
    
    col_index = config.availability_column
    col_letter = chr(65 + col_index)
    rules = []
    common_range = [{
        'sheetId': worksheet.id,
        'startRowIndex': 1,
        'endRowIndex': row_count + 1,
        'startColumnIndex': 0,
        'endColumnIndex': len(config.column_headers)
    }]

    # Available rows - alternating green shades
    rules.extend([
        {  # Even rows - darker green
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'type': 'CUSTOM_FORMULA',
                            'values': [{"userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.AVAILABLE.value}", ISEVEN(ROW()))'}]
                        },
                        'format': {
                            'backgroundColor': DARK_GREEN,
                            'textFormat': {'foregroundColor': WHITE_TEXT, 'bold': True}
                        }
                    }
                }
            }
        },
        {  # Odd rows - lighter green
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'values': [{"userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.AVAILABLE.value}", ISODD(ROW()))'}]
                        },
                        'format': {
                            'backgroundColor': LIGHT_GREEN,
                            'textFormat': {'foregroundColor': AVAILABLE_TEXT_COLOR, 'bold': True}
                        }
                    }
                }
            }
        }
    ])

    # Unavailable rows - alternating red shades
    rules.extend([
        {  # Even rows - darker red
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'values': [{"userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.NOT_AVAILABLE.value}", ISEVEN(ROW()))'}]
                        },
                        'format': {
                            'backgroundColor': DARK_RED,
                            'textFormat': {'foregroundColor': WHITE_TEXT, 'bold': True}
                        }
                    }
                }
            }
        },
        {  # Odd rows - lighter red
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'values': [{"userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.NOT_AVAILABLE.value}", ISODD(ROW()))'}]
                        },
                        'format': {
                            'backgroundColor': LIGHT_RED,
                            'textFormat': {'foregroundColor': UNAVAILABLE_TEXT_COLOR, 'bold': True}
                        }
                    }
                }
            }
        }
    ])

    return rules
    
def _create_optimized_borders(worksheet, row_count: int, col_count: int) -> dict:
    """Apply minimal border styling."""
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
    """Freeze header row."""
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
    """Set column alignment and text wrapping."""
    alignments = {
        0: ('LEFT', 'WRAP'),
        1: ('RIGHT', 'OVERFLOW_CELL'),
        2: ('CENTER', 'OVERFLOW_CELL'),
        3: ('CENTER', 'OVERFLOW_CELL'),
        4: ('CENTER', 'OVERFLOW_CELL')
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
                    'wrapStrategy': wrap_strategy
                }
            },
            'fields': 'userEnteredFormat(horizontalAlignment,wrapStrategy)'
        }
    } for col, (alignment, wrap_strategy) in alignments.items()]

def _create_timestamp_format(worksheet, row: int) -> dict:
    """Format timestamp row."""
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

# =============================== MAIN FLOW ================================
def main():
    """Main execution flow."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

    if not (credentials := load_google_credentials()):
        return

    # Authorize and create a gspread client
    client = gspread.authorize(credentials)

    for dispensary in DISPENSARIES:
        start_time = time.monotonic()
        logging.info(f"Starting {dispensary.name}")
        
        try:
            # Scrape data from the dispensary
            if data := dispensary.scrape_method(dispensary.url, dispensary.use_cloudscraper):
                # Open the spreadsheet and get (or create) the worksheet
                spreadsheet = client.open_by_key(dispensary.spreadsheet_id)
                worksheet = _get_or_create_worksheet(spreadsheet, dispensary.sheet_name)
                
                # Define row_count as the number of data rows and timestamp_row as the row after data
                row_count = len(data)
                timestamp_row = row_count + 1

                update_start = time.monotonic()
                # Call update_google_sheet with all required parameters.
                update_google_sheet(dispensary, worksheet, [], row_count, timestamp_row)
                logging.info(f"Updated {dispensary.name} in {time.monotonic() - update_start:.2f}s")
        except Exception as e:
            logging.error(f"Error processing {dispensary.name}: {str(e)}")
        
        logging.info(f"Total {dispensary.name} time: {time.monotonic() - start_time:.2f}s")

if __name__ == "__main__":
    main()
