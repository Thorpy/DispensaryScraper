# Dispensary Scraper 🍁

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/Thorpy/DispensaryScraper)](https://github.com/Thorpy/DispensaryScraper/commits/main)

Automated product data scraper for medical dispensaries with real-time Google Sheets integration.

**Live Sheets** (view-only):  
🔗 [Mamedica Products](https://docs.google.com/spreadsheets/d/1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw/edit?usp=sharing)  
🔗 [Montu Products](https://docs.google.com/spreadsheets/d/1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU/edit?usp=sharing)  
🔗 [CB1 Shop](http://cb1.shop/) (3rd party sheet)  
🔗 [Integro] (https://docs.google.com/spreadsheets/d/15sxwI1IGcYTz-SC9bY0dO2ipEUGVW-_O/htmlview?pli=1#gid=404951805)(3rd party sheet)

## Features ✨
- Real-time Google Sheets updates
- **Optimized Batch Updates** for data and formatting (drastically improved performance)
- Mobile-optimized formatting
- Automatic price/availability tracking with robust error handling
- Cloudflare bypass support via cloudscraper
- Optimized HTTP client with retries for improved resilience

## What's New 🚀
- **Batch Updates for Google Sheets**:  
  The `update_google_sheet` function has been revamped to use `batch_update` and `update_cells` methods. By combining data and formatting updates into fewer API calls, update times have been reduced from around 80 seconds to just a few seconds even for large datasets.
- Enhanced error logging and retry mechanisms.

## Installation ⚙️
```bash
git clone https://github.com/Thorpy/DispensaryScraper.git
cd DispensaryScraper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration 🔧

### Step 1: Enable Google Sheets API and Create a Service Account
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Navigate to **APIs & Services > Library**.
4. Search for **Google Sheets API** and click **Enable**.

### Step 2: Create a Service Account and Download Credentials
1. In the Cloud Console, go to **APIs & Services > Credentials**.
2. Click **Create Credentials** and select **Service Account**.
3. Fill in a name and description, then click **Create**.
4. (Optional) Skip role assignments if not needed and click **Done**.
5. Click on your newly created service account to view its details.
6. Under the **Keys** section, click **Add Key > Create New Key**, choose **JSON**, and click **Create**.
7. Save the downloaded JSON file as `credentials.json` in your project directory.

### Step 3: Share Your Google Sheet with the Service Account
1. Open your target Google Sheet.
2. Click the **Share** button.
3. Add the service account's email (found in `credentials.json` under `client_email`) with **Editor** permissions.

### Step 4: Set Up Environment Variables
You need to provide your configuration values to the application. You can create a `.env` file manually in your project directory or run the following one-liner command in your terminal (for Linux, macOS, or WSL):

```bash
echo "GOOGLE_CREDENTIALS_PATH=\"./credentials.json\"\nMAMEDICA_SHEET_ID=\"your_mamedica_sheet_id\"\nMONTU_SHEET_ID=\"your_montu_sheet_id\"" > .env
```

If you're using Windows, you can create a file named `.env` in your project directory and add the following content:

```bash
GOOGLE_CREDENTIALS_PATH="./credentials.json"
MAMEDICA_SHEET_ID="your_mamedica_sheet_id"
MONTU_SHEET_ID="your_montu_sheet_id"
```

Replace `your_mamedica_sheet_id` and `your_montu_sheet_id` with the actual sheet IDs (the long string in the URL of your Google Sheet, e.g., `https://docs.google.com/spreadsheets/d/<sheet_id>/edit`).

## Usage 🚀
```bash
python dispensary_scraper.py
```

Sample output:
```
2024-01-24 12:00:00,000 - INFO - Starting Mamedica
2024-01-24 12:00:05,123 - INFO - Updated Mamedica in 3.45s
2024-01-24 12:00:10,456 - INFO - Starting Montu
2024-01-24 12:00:15,789 - INFO - Updated Montu in 2.34s
```

## License 📄
MIT License - see [LICENSE](LICENSE)

---

**Maintained by Thorpy** • [Report Issues](https://github.com/Thorpy/DispensaryScraper/issues)
