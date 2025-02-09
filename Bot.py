# -*- coding: utf-8 -*-
"""Configurable cannabis dispensary price scraper with Google Sheets integration."""

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
    currency_columns: List[int]
    column_alignment: Dict[int, Tuple[str, str]]
    header_bg_color: Dict[str, float]
    header_text_color: Dict[str, float]
    even_stripe_color: Dict[str, float]
    odd_stripe_color: Dict[str, float]
    availability_column: Optional[int] = None
    availability_colors: Optional[Dict[str, Dict[str, Dict[str, Dict[str, float]]]]] = None
    timestamp_color: Dict[str, float] = None
    use_cloudscraper: bool = True

class AvailabilityStatus(Enum):
    AVAILABLE = 'Available'
    NOT_AVAILABLE = 'Not Available'

DEFAULT_HEADER_BG = {'red': 0.12, 'green': 0.24, 'blue': 0.35}
DEFAULT_HEADER_TEXT = {'red': 1, 'green': 1, 'blue': 1}
DEFAULT_EVEN_STRIPE = {'red': 0.97, 'green': 0.97, 'blue': 0.97}
DEFAULT_ODD_STRIPE = {'red': 1, 'green': 1, 'blue': 1}
DEFAULT_TIMESTAMP_COLOR = {'red': 0.5, 'green': 0.5, 'blue': 0.5}

DISPENSARIES = [
    DispensaryConfig(
        name="Mamedica",
        url="https://mamedica.co.uk/repeat-prescription/",
        spreadsheet_id=os.getenv('MAMEDICA_SHEET_ID', '1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw'),
        sheet_name="Mamedica List",
        scrape_method=lambda url, cfg: scrape_mamedica_products(url, cfg),
        column_headers=['Product', 'Price'],
        column_widths={0: 380, 1: 60},
        currency_columns=[1],
        column_alignment={0: ('LEFT', 'WRAP'), 1: ('RIGHT', 'OVERFLOW_CELL')},
        header_bg_color=DEFAULT_HEADER_BG,
        header_text_color=DEFAULT_HEADER_TEXT,
        even_stripe_color={'red': 0.9, 'green': 0.9, 'blue': 0.9},
        odd_stripe_color={'red': 1, 'green': 1, 'blue': 1},
        timestamp_color=DEFAULT_TIMESTAMP_COLOR
    ),
    DispensaryConfig(
        name="Montu",
        url="https://store.montu.uk/products.json",
        spreadsheet_id=os.getenv('MONTU_SHEET_ID', '1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU'),
        sheet_name="Montu List",
        scrape_method=lambda url, cfg: scrape_montu_products(url, cfg),
        column_headers=['Product', 'Price', 'THC %', 'CBD %', 'Availability'],
        column_widths={0: 280, 1: 100, 2: 80, 3: 80, 4: 120},
        currency_columns=[1],
        column_alignment={0: ('LEFT', 'WRAP'), 1: ('RIGHT', 'OVERFLOW_CELL'), 
                        2: ('CENTER', 'OVERFLOW_CELL'), 3: ('CENTER', 'OVERFLOW_CELL'),
                        4: ('CENTER', 'OVERFLOW_CELL')},
        header_bg_color=DEFAULT_HEADER_BG,
        header_text_color=DEFAULT_HEADER_TEXT,
        availability_column=4,
        availability_colors={
            'available': {
                'even': {'bg': {'red': 0.7, 'green': 0.9, 'blue': 0.7}, 'text': {'red': 0, 'green': 0.4, 'blue': 0}},
                'odd': {'bg': {'red': 0.85, 'green': 0.95, 'blue': 0.85}, 'text': {'red': 0, 'green': 0.55, 'blue': 0}}
            },
            'unavailable': {
                'even': {'bg': {'red': 1, 'green': 0.7, 'blue': 0.7}, 'text': {'red': 0.6, 'green': 0, 'blue': 0}},
                'odd': {'bg': {'red': 1, 'green': 0.9, 'blue': 0.9}, 'text': {'red': 0.65, 'green': 0, 'blue': 0}}
            }
        },
        even_stripe_color=DEFAULT_EVEN_STRIPE,
        odd_stripe_color=DEFAULT_ODD_STRIPE,
        timestamp_color=DEFAULT_TIMESTAMP_COLOR
    )
]

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
REQUEST_TIMEOUT = 25
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

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

def scrape_mamedica_products(url: str, config: DispensaryConfig) -> List[Tuple]:
    """Scrape products from Mamedica website."""
    client = create_http_client(config.use_cloudscraper)
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

    except requests.exceptions.RequestException as error:
        logging.error("Mamedica request error: %s", error)
        return []
    except Exception as error:
        logging.error("Mamedica processing error: %s", error)
        return []

def scrape_montu_products(url: str, config: DispensaryConfig) -> List[Tuple]:
    """Scrape products from Montu website."""
    client = create_http_client(config.use_cloudscraper)
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

    except requests.exceptions.RequestException as error:
        logging.error("Montu request error: %s", error)
        return []
    except Exception as error:
        logging.error("Montu processing error: %s", error)
        return []

def update_google_sheet(config: DispensaryConfig, worksheet, products: List[Tuple]):
    """Update Google Sheet with data and formatting."""
    try:
        data = [config.column_headers] + [list(p) for p in products]
        timestamp_row = len(data) + 2
        data += [[]] * 2 + [[datetime.now().strftime("Updated: %H:%M %d/%m/%Y")]]

        worksheet.batch_clear(["A:Z"])
        worksheet.update(data, 'A1')

        format_requests = [
            *create_header_format(config, worksheet),
            *create_column_widths(config, worksheet),
            *create_currency_formats(config, worksheet, len(products)),
            *create_conditional_formatting(config, worksheet, len(products)),
            create_borders(worksheet, len(products), len(config.column_headers)),
            create_frozen_header(worksheet),
            create_timestamp_format(config, worksheet, timestamp_row),
            *create_text_alignment(config, worksheet, len(products))
        ]

        if valid_requests := [r for r in format_requests if r]:
            worksheet.spreadsheet.batch_update({'requests': valid_requests})

        logging.info(f"{config.name} sheet updated successfully")

    except gspread.exceptions.APIError as error:
        logging.error("Google Sheets API error: %s", error)
    except Exception as error:
        logging.error("Sheet update failed: %s", error)

# ========================== FORMATTING HELPERS ============================
def get_or_create_worksheet(spreadsheet, sheet_name: str) -> gspread.Worksheet:
    """Get existing worksheet or create new if not found."""
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(sheet_name, 100, 20)

def create_header_format(config: DispensaryConfig, worksheet) -> List[dict]:
    """Create header row formatting."""
    return [{
        'repeatCell': {
            'range': {
                'sheetId': worksheet.id,
                'startRowIndex': 0,
                'endRowIndex': 1,
                'startColumnIndex': 0,
                'endColumnIndex': len(config.column_headers)
            },
            'cell': {
                'userEnteredFormat': {
                    'backgroundColor': config.header_bg_color,
                    'textFormat': {
                        'foregroundColor': config.header_text_color,
                        'bold': True,
                        'fontSize': 12
                    },
                    'horizontalAlignment': 'CENTER',
                    'wrapStrategy': 'WRAP'
                }
            },
            'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,wrapStrategy)'
        }
    }]

def create_column_widths(config: DispensaryConfig, worksheet) -> List[dict]:
    """Set column widths from configuration."""
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

def create_currency_formats(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    """Apply currency formatting to specified columns."""
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

def create_conditional_formatting(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    """Create all conditional formatting rules."""
    rules = []
    if config.availability_column is not None:
        rules.extend(create_availability_rules(config, worksheet, row_count))
    else:
        rules.append(create_zebra_stripes(config, worksheet, row_count))
    return rules

def create_availability_rules(config: DispensaryConfig, worksheet, row_count: int) -> List[dict]:
    """Create availability-based formatting rules."""
    if not config.availability_colors:
        return []

    col_letter = chr(65 + config.availability_column)
    rules = []
    
    for status, colors in config.availability_colors.items():
        for parity in ['even', 'odd']:
            rules.append({
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
                                'values': [{
                                    "userEnteredValue": f'=AND(${col_letter}2="{getattr(AvailabilityStatus, status.upper()).value}", IS{parity.upper()}(ROW()))'
                                }]
                            },
                            'format': {
                                'backgroundColor': colors[parity]['bg'],
                                'textFormat': {
                                    'foregroundColor': colors[parity]['text'],
                                    'bold': True
                                }
                            }
                        }
                    }
                }
            })
    return rules

def _create_zebra_stripes(config, worksheet, row_count: int, col_count: int) -> dict:
    """Create alternating row colors for dispensaries without an availability column."""
    if config.availability_column is not None:
        return None  # Handled by availability rules

    # For Mamedica, use a more noticeable grey difference
    if config.name == "Mamedica":
        zebra_color = {'red': 0.9, 'green': 0.9, 'blue': 0.9}
        text_color = {'red': 0.15, 'green': 0.15, 'blue': 0.15}
    else:
        zebra_color = ALTERNATING_ROW_COLOR
        text_color = {'red': 0.2, 'green': 0.2, 'blue': 0.2}

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
                        'backgroundColor': zebra_color,
                        'textFormat': {'foregroundColor': text_color}
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

    # For Montu, use custom text colors; otherwise, use defaults.
    if config.name == "Montu":
        available_even_text = {'red': 0.0, 'green': 0.65, 'blue': 0.0}
        available_odd_text  = {'red': 0.0, 'green': 0.55, 'blue': 0.0}
        unavailable_even_text = {'red': 0.65, 'green': 0.0, 'blue': 0.0}
        unavailable_odd_text  = {'red': 0.55, 'green': 0.0, 'blue': 0.0}
    else:
        available_even_text = WHITE_TEXT
        available_odd_text  = AVAILABLE_TEXT_COLOR
        unavailable_even_text = WHITE_TEXT
        unavailable_odd_text  = UNAVAILABLE_TEXT_COLOR

    # Available rows - alternating green shades
    rules.extend([
        {  # Even rows
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'type': 'CUSTOM_FORMULA',
                            'values': [{
                                "userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.AVAILABLE.value}", ISEVEN(ROW()))'
                            }]
                        },
                        'format': {
                            'backgroundColor': DARK_GREEN,
                            'textFormat': {'foregroundColor': available_even_text, 'bold': True}
                        }
                    }
                }
            }
        },
        {  # Odd rows
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'type': 'CUSTOM_FORMULA',
                            'values': [{
                                "userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.AVAILABLE.value}", ISODD(ROW()))'
                            }]
                        },
                        'format': {
                            'backgroundColor': LIGHT_GREEN,
                            'textFormat': {'foregroundColor': available_odd_text, 'bold': True}
                        }
                    }
                }
            }
        }
    ])

    # Unavailable rows - alternating red shades
    rules.extend([
        {  # Even rows
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'type': 'CUSTOM_FORMULA',
                            'values': [{
                                "userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.NOT_AVAILABLE.value}", ISEVEN(ROW()))'
                            }]
                        },
                        'format': {
                            'backgroundColor': DARK_RED,
                            'textFormat': {'foregroundColor': unavailable_even_text, 'bold': True}
                        }
                    }
                }
            }
        },
        {  # Odd rows
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': common_range,
                    'booleanRule': {
                        'condition': {
                            'type': 'CUSTOM_FORMULA',
                            'values': [{
                                "userEnteredValue": f'=AND(${col_letter}2="{AvailabilityStatus.NOT_AVAILABLE.value}", ISODD(ROW()))'
                            }]
                        },
                        'format': {
                            'backgroundColor': LIGHT_RED,
                            'textFormat': {'foregroundColor': unavailable_odd_text, 'bold': True}
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

    client = gspread.authorize(credentials)

    for dispensary in DISPENSARIES:
        try:
            start_time = time.monotonic()
            products = dispensary.scrape_method(dispensary.url, dispensary)
            if products:
                spreadsheet = client.open_by_key(dispensary.spreadsheet_id)
                worksheet = spreadsheet.worksheet(dispensary.sheet_name)
                update_google_sheet(dispensary, worksheet, products)
            logging.info(f"{dispensary.name} completed in {time.monotonic()-start_time:.2f}s")
        except Exception as e:
            logging.error(f"Error processing {dispensary.name}: {str(e)}")

if __name__ == "__main__":
    main()
