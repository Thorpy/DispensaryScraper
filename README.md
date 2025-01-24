# Dispensary Scraper 🍁

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/Thorpy/DispensaryScraper)](https://github.com/Thorpy/DispensaryScraper/commits/main)

Automated product data scraper for medical dispensaries with real-time Google Sheets integration.

**Live Sheets** (view-only):  
🔗 [Mamedica Products](https://docs.google.com/spreadsheets/d/1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw/edit?usp=sharing)  
🔗 [Montu Products](https://docs.google.com/spreadsheets/d/1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU/edit?usp=sharing)  
🔗 [CB1 Shop](http://cb1.shop/) (3rd party sheet)

![Screenshot](https://via.placeholder.com/800x500.png?text=Spreadsheet+Preview)

## Features ✨
- Real-time Google Sheets updates
- Mobile-optimized formatting
- Automatic price/availability tracking
- Error handling with retries

## Installation ⚙️
```bash
git clone https://github.com/Thorpy/DispensaryScraper.git
cd DispensaryScraper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration 🔧
1. Create Google Service Account credentials
2. Share your sheet with the service account email
3. Add credentials to `.env`:
```bash
GOOGLE_CREDENTIALS_PATH="./credentials.json"
MAMEDICA_SHEET_ID="your_sheet_id"
MONTU_SHEET_ID="your_sheet_id"
```

## Usage 🚀
```bash
python dispensary_scraper.py
```

Sample output:
```
2024-01-24 12:00:00,000 - INFO - Processing Mamedica
2024-01-24 12:00:05,123 - INFO - Updated 142 products
2024-01-24 12:00:10,456 - INFO - Processing Montu
2024-01-24 12:00:15,789 - INFO - Updated 89 products
```

## License 📄
MIT License - see [LICENSE](LICENSE)

---
**Maintained by Thorpy** • [Report Issues](https://github.com/Thorpy/DispensaryScraper/issues)
