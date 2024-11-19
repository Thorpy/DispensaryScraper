# Dispensary Scraper

A Python script for scraping product data from dispensary websites and updating Google Sheets with the latest information.

IF YOU JUST WANT TO SEE THE SHEETS:

  **[Mamedica](https://docs.google.com/spreadsheets/d/1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw/edit?usp=sharing)**
  
  **[Montu](https://docs.google.com/spreadsheets/d/1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU/edit?usp=sharing)**
  
  **[CB1](http://cb1.shop/)** - note this is their own Google sheet, I didn't make it, it's only included for curious people that might need a link to their store (plus it's much prettier than anything I make!)

## Requirements

- Python 3.x
- Required Python packages:
  - `requests`
  - `beautifulsoup4`
  - `google-auth`
  - `gspread`

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Thorpy/DispensaryScraper.git
cd dispensary-scraper
```

### 2. Install Dependencies

Make sure you have Python and pip installed, then run:

```bash
pip install requests beautifulsoup4 google-auth gspread
```

### 3. Generate Google Sheets API Credentials

To allow the script to interact with Google Sheets, you'll need to create a Google Cloud project and generate a service account key:

1. **Go to the [Google Cloud Console](https://console.cloud.google.com/)**.
2. **Create a new project**:
   - Click on the project dropdown on the top left and select "New Project".
   - Name your project and click "Create".

3. **Enable the Google Sheets API**:
   - In the left sidebar, navigate to `APIs & Services` > `Library`.
   - Search for "Google Sheets API" and click on it.
   - Click the "Enable" button.

4. **Create a Service Account**:
   - In the left sidebar, navigate to `APIs & Services` > `Credentials`.
   - Click on "Create Credentials" and select "Service Account".
   - Fill in the service account details and click "Create".
   - (Optional) Grant this service account access to project resources, then click "Continue".

5. **Generate the Service Account Key**:
   - In the Service Accounts list, click on the service account you just created.
   - Go to the "Keys" tab and click on "Add Key" > "JSON".
   - A JSON file will be downloaded. This is your credentials file.

6. **Share Your Google Sheet**:
   - Create a new Google Sheet for each dispensary you wish to scrape.
   - Click on the "Share" button in the top right corner.
   - Share each sheet with the service account email (found in the JSON file) by adding it as a collaborator.

### 4. Update the Credentials

Place the downloaded JSON credentials file in the same directory as your script and rename it to `credentials.json`.

### 5. Configure the Script

- Open the script and update the `dispensaries` list with the URLs and corresponding Google Sheets IDs for any dispensaries you wish to scrape. YOU WILL NEED YOUR OWN SCRAPE LOGIC for custom dispensaries.

### 6. Run the Script

Execute the script using the following command:

```bash
python your_script_name.py
```

### 7. Terminal Output

You will receive updates in the terminal about the process steps, including when each dispensary is being processed and when each sheet is successfully updated.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
