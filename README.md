# Dispensary Scraper

A Python script for scraping product data from dispensary websites and updating Google Sheets with the latest information.

IF YOU JUST WANT TO SEE THE SHEETS:
**[Mamedica:](https://docs.google.com/spreadsheets/d/1VmxZ_1crsz4_h-RxEdtxAI6kdeniUcHxyttlR1T1rJw/edit?usp=sharing)**
**[Montu](https://docs.google.com/spreadsheets/d/1Ae_2QK40_VFgn1t4NAkPIvi0FwGu7mh67OK5hOEaQLU/edit?usp=sharing)**

## Requirements

- Python 3.x
- Required Python packages:
  - `requests`
  - `beautifulsoup4`
  - `pandas`
  - `google-auth`
  - `google-api-python-client`

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Thorpy/DispensaryScraper.git
cd dispensary-scraper
```

### 2. Install Dependencies

Make sure you have Python and pip installed, then run:

```bash
pip install requests beautifulsoup4 pandas google-auth google-api-python-client
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

- Open the script and update the `DISPENSARIES` list with the URLs and corresponding Google Sheets IDs for any dispensaries you wish to scrape. This allows for easy expansion to add more dispensaries in the future.

### 6. Run the Script

Execute the script using the following command:

```bash
python your_script_name.py
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
