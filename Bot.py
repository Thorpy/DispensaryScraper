# -*- coding: utf-8 -*-
import os
import requests
import logging
import random
import time
from datetime import datetime
from typing import List, Tuple, Optional
from google.oauth2.service_account import Credentials
import gspread
from bs4 import BeautifulSoup
import re
import cloudscraper  # New import for bypassing Cloudflare

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

CREDENTIALS_PATH = os.getenv(
    'GOOGLE_CREDENTIALS_PATH',
    os.path.join(os.path.dirname(__file__), 'credentials.json')
)

class Dispensary:
    def __init__(self, name: str, url: str, spreadsheet_id: str, sheet_name: str,
                 scrape_method: callable, columns: List[str],
                 availability_col: Optional[int] = None):
        self.name = name
        self.url = url
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.scrape_method = scrape_method
        self.columns = columns
        self.availability_col = availability_col

def load_credentials() -> Optional[Credentials]:
    """Load Google Sheets API credentials with error handling."""
    try:
        return Credentials.from_service_account_file(
            CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
    except Exception as e:
        logging.error(f"Credential loading failed: {e}")
        return None

def scrape_mamedica(url: str) -> List[Tuple]:
    """Scrape Mamedica products using cloudscraper to bypass Cloudflare."""
    try:
        # Create a cloudscraper instance
        scraper = cloudscraper.create_scraper()
        
        # Optionally add a random delay to mimic human browsing
        time.sleep(random.uniform(1.0, 2.5))
        
        response = scraper.get(url, timeout=15)
        response.raise_for_status()

        # Verify we received the actual prescription page
        if "repeat-prescription" not in response.text.lower():
            logging.warning("Mamedica: Received unexpected page content")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        products = set()

        # Parse products
        for option in soup.find_all('option'):
            if not (value := option.get('value')) or '|' not in value:
                continue

            try:
                product_name, price_value = map(str.strip, value.split('|'))
                price = round(float(price_value), 2)
                products.add((product_name, price))
            except (IndexError, ValueError, TypeError) as e:
                logging.warning(f"Mamedica: Error parsing product - {str(e)}")
                continue

        return sorted(products, key=lambda x: x[0])

    except requests.exceptions.RequestException as e:
        logging.error(f"Mamedica: Request failed - {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Mamedica: Unexpected error - {str(e)}")
        return []

def scrape_montu(url: str) -> List[Tuple[str, float, str, str, str]]:
    """Scrape Montu products with pagination and error handling."""
    all_products = []
    page = 1
    retries = 3

    while retries > 0:
        try:
            response = requests.get(f"{url}?page={page}", timeout=15)
            response.raise_for_status()
            products = response.json().get('products', [])

            if not products:
                break

            for product in products:
                try:
                    title = product.get('title', '').strip()
                    variant = product['variants'][0]
                    price = float(variant['price'].strip())
                    body_html = product.get('body_html', '')

                    thc_match = re.search(r'THC\s*([\d.]+)%', body_html, re.IGNORECASE)
                    cbd_match = re.search(r'CBD\s*([\d.]+)%', body_html, re.IGNORECASE)

                    thc = float(thc_match.group(1)) if thc_match else None
                    cbd = float(cbd_match.group(1)) if cbd_match else None

                    all_products.append((
                        title,
                        price,
                        f"{thc:.1f}%" if thc is not None else "Unknown",
                        f"{cbd:.1f}%" if cbd is not None else "Unknown",
                        'Available' if variant['available'] else 'Not Available'
                    ))
                except (KeyError, IndexError, ValueError) as e:
                    logging.warning(f"Error parsing product: {e}")

            page += 1
            retries = 3
        except (requests.RequestException, ValueError):
            retries -= 1
            logging.warning(f"Retrying Montu page {page} ({retries} left)...")

    return sorted(all_products, key=lambda x: (x[4] == 'Not Available', x[0]))

def create_format_requests(worksheet, data: List[Tuple], columns: List[str],
                          availability_col: Optional[int]) -> List[dict]:
    """Generate Google Sheets formatting requests with API-compliant rules."""
    sheet_id = worksheet.id
    requests_list = []

    # Base cell formatting
    requests_list.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0,
                'endRowIndex': len(data) + 3 if data else 3,
                'startColumnIndex': 0,
                'endColumnIndex': len(columns)
            },
            'cell': {
                'userEnteredFormat': {
                    'wrapStrategy': 'WRAP',
                    'verticalAlignment': 'MIDDLE',
                    'horizontalAlignment': 'CENTER',
                    'borders': {
                        'top': {'style': 'SOLID', 'width': 1, 'color': {'red': 0.8, 'green': 0.8, 'blue': 0.8}},
                        'bottom': {'style': 'SOLID', 'width': 1, 'color': {'red': 0.8, 'green': 0.8, 'blue': 0.8}},
                        'left': {'style': 'SOLID', 'width': 1, 'color': {'red': 0.8, 'green': 0.8, 'blue': 0.8}},
                        'right': {'style': 'SOLID', 'width': 1, 'color': {'red': 0.8, 'green': 0.8, 'blue': 0.8}}
                    }
                }
            },
            'fields': 'userEnteredFormat(wrapStrategy,verticalAlignment,horizontalAlignment,borders)'
        }
    })

    # Header styling
    requests_list.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 0,
                'endRowIndex': 1,
                'startColumnIndex': 0,
                'endColumnIndex': len(columns)
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {
                        'bold': True,
                        'fontSize': 12,
                        'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
                    },
                    'horizontalAlignment': 'CENTER',
                    'backgroundColor': {'red': 0.1, 'green': 0.2, 'blue': 0.3},
                    'borders': {
                        'top': {'style': 'SOLID', 'width': 2, 'color': {'red': 0, 'green': 0, 'blue': 0}},
                        'bottom': {'style': 'SOLID', 'width': 2, 'color': {'red': 0, 'green': 0, 'blue': 0}}
                    }
                }
            },
            'fields': 'userEnteredFormat(textFormat,horizontalAlignment,backgroundColor,borders)'
        }
    })

    # Column widths
    column_widths = {0: 180, 1: 100, 2: 80, 3: 80, 4: 110}
    for col, width in column_widths.items():
        if col < len(columns):
            requests_list.append({
                'updateDimensionProperties': {
                    'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': col},
                    'properties': {'pixelSize': width},
                    'fields': 'pixelSize'
                }
            })

    if data:
        # Alternating row colors (API-compliant)
        requests_list.append({
            'addConditionalFormatRule': {
                'rule': {
                    'ranges': [{
                        'sheetId': sheet_id,
                        'startRowIndex': 1,
                        'endRowIndex': len(data) + 1
                    }],
                    'booleanRule': {
                        'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue': '=ISEVEN(ROW())'}]},
                        'format': {
                            'backgroundColor': {'red': 0.98, 'green': 0.98, 'blue': 0.98}
                        }
                    }
                }
            }
        })

        # Price formatting
        requests_list.append({
            'repeatCell': {
                'range': {'sheetId': sheet_id, 'startRowIndex': 1, 'startColumnIndex': 1},
                'cell': {
                    'userEnteredFormat': {
                        'numberFormat': {'type': 'CURRENCY', 'pattern': '"£"#,##0.00'},
                        'horizontalAlignment': 'RIGHT'
                    }
                },
                'fields': 'userEnteredFormat(numberFormat,horizontalAlignment)'
            }
        })

        # Availability formatting (API-compliant)
        if availability_col is not None:
            availability_range = {
                'sheetId': sheet_id,
                'startRowIndex': 1,
                'startColumnIndex': availability_col
            }
            requests_list.extend([
                {
                    'addConditionalFormatRule': {
                        'rule': {
                            'ranges': [availability_range],
                            'booleanRule': {
                                'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': 'Not Available'}]},
                                'format': {
                                    'backgroundColor': {'red': 1, 'green': 0.9, 'blue': 0.9},
                                    'textFormat': {'bold': True}
                                }
                            }
                        }
                    }
                },
                {
                    'addConditionalFormatRule': {
                        'rule': {
                            'ranges': [availability_range],
                            'booleanRule': {
                                'condition': {'type': 'TEXT_EQ', 'values': [{'userEnteredValue': 'Available'}]},
                                'format': {
                                    'backgroundColor': {'red': 0.85, 'green': 0.95, 'blue': 0.85},
                                    'textFormat': {'bold': True}
                                }
                            }
                        }
                    }
                }
            ])

    # Timestamp formatting
    timestamp_row = len(data) + 2 if data else 2
    requests_list.append({
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': timestamp_row,
                'endRowIndex': timestamp_row + 1,
                'startColumnIndex': 0,
                'endColumnIndex': 1
            },
            'cell': {
                'userEnteredFormat': {
                    'textFormat': {
                        'italic': True,
                        'bold': True,
                        'fontSize': 10,
                        'foregroundColor': {'red': 0.5, 'green': 0.5, 'blue': 0.5}
                    },
                    'backgroundColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}
                }
            },
            'fields': 'userEnteredFormat(textFormat,backgroundColor)'
        }
    })

    # Freeze header row
    requests_list.append({
        'updateSheetProperties': {
            'properties': {'sheetId': sheet_id, 'gridProperties': {'frozenRowCount': 1}},
            'fields': 'gridProperties.frozenRowCount'
        }
    })

    return requests_list

def update_google_sheet(creds: Credentials, dispensary: Dispensary, data: List[Tuple]):
    """Update Google Sheet with data and formatting."""
    try:
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(dispensary.spreadsheet_id)
        worksheet = spreadsheet.worksheet(dispensary.sheet_name)

        # Prepare data with empty row before timestamp
        timestamp = datetime.now().strftime("Updated on: %H:%M %d/%m/%Y")
        updates = [dispensary.columns] + data + [[]] + [[timestamp]]

        worksheet.clear()
        worksheet.update(updates, 'A1')

        # Apply formatting
        format_requests = create_format_requests(worksheet, data, dispensary.columns, dispensary.availability_col)
        if format_requests:
            spreadsheet.batch_update({'requests': format_requests})

        logging.info(f"Successfully updated {dispensary.name} with {len(data)} products")

    except gspread.exceptions.APIError as e:
        logging.error(f"Google API Error: {e.response.text}")
    except Exception as e:
        logging.error(f"Failed to update {dispensary.name}: {str(e)}")

def main():
    creds = load_credentials()
    if not creds:
        return

    dispensaries = [
        Dispensary(
            name="Mamedica",
            url="https://mamedica.co.uk/repeat-prescription/",
            spreadsheet_id=os.getenv('MAMEDICA_SHEET_ID', '1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw'),
            sheet_name="Mamedica List",
            scrape_method=scrape_mamedica,
            columns=['Product', 'Price']
        ),
        Dispensary(
            name="Montu",
            url="https://store.montu.uk/products.json",
            spreadsheet_id=os.getenv('MONTU_SHEET_ID', '1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU'),
            sheet_name="Montu List",
            scrape_method=scrape_montu,
            columns=['Product', 'Price', 'THC %', 'CBD %', 'Availability'],
            availability_col=4
        )
    ]

    for dispensary in dispensaries:
        try:
            logging.info(f"Processing {dispensary.name}")
            if data := dispensary.scrape_method(dispensary.url):
                update_google_sheet(creds, dispensary, data)
            else:
                logging.warning(f"No data found for {dispensary.name}")
        except Exception as e:
            logging.error(f"Error processing {dispensary.name}: {e}")

if __name__ == "__main__":
    main()
