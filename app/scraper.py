import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Base Directories
CSV_DIR = os.path.join(os.path.dirname(__file__), "csv")
TARGET_URL = "https://usicecenter.gov/Products/AntarcIcebergs"

def get_filename_from_headers(response):
    """Extract filename from Content-Disposition header if available."""
    content_disp = response.headers.get("Content-Disposition")
    if content_disp:
        fname_match = re.findall("filename=(.+)", content_disp)
        if fname_match:
            return fname_match[0].strip('\'"')
    return None

def download_file(url):
    """Download a file from a URL, saving it to the csv directory."""
    os.makedirs(CSV_DIR, exist_ok=True)
    
    try:
        # Perform request with stream enabled for safety
        response = requests.get(url, stream=True, timeout=15, verify=False) # verify=False because USNIC sometimes has SSL certificate issues
        response.raise_for_status()
        
        # Try to resolve filename from headers or fallback to URL path parsing
        filename = get_filename_from_headers(response)
        if not filename:
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            
        # Clean filename and verify it matches the iceberg CSV pattern
        if not filename or not filename.lower().endswith(".csv"):
            # Fallback name if it cannot be parsed
            filename = f"AntarcticIcebergs_{requests.utils.quote(url[-10:])}.csv"
            
        # Clean standard filename
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        
        filepath = os.path.join(CSV_DIR, filename)
        
        # Write file in chunks to avoid high memory spikes
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        print(f"Successfully downloaded: {filename}")
        return filepath, filename
    except Exception as e:
        print(f"Error downloading file from {url}: {e}")
        return None, None

def scrape_usnic_latest_csv():
    """
    Scrapes the USNIC Antarctic Iceberg page to discover and download the latest CSV.
    Returns: (status_message, downloaded_filepath, filename)
    """
    print(f"Connecting to U.S. National Ice Center: {TARGET_URL}")
    try:
        # Fetch the product portal page
        # Ignore SSL certificate verification issues which are common on public gov domains
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(TARGET_URL, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Find all active hyperlinks
        a_tags = soup.find_all("a", href=True)
        csv_links = []
        
        for tag in a_tags:
            href = tag["href"]
            text = tag.get_text().lower()
            
            # Check for CSV indicators
            if ".csv" in href.lower() or "csv" in text or "downloadiceberg" in href.lower():
                full_url = urljoin(TARGET_URL, href)
                csv_links.append(full_url)
                
        # Remove duplicates
        csv_links = list(set(csv_links))
        
        if not csv_links:
            return "No CSV files found in the current USNIC product catalog page.", None, None
            
        print(f"Discovered {len(csv_links)} prospective CSV files. Downloading the first match...")
        
        # Typically the main/latest weekly CSV is the first one linked, or we can choose the one containing 'Antarctic'
        best_link = None
        for link in csv_links:
            if "antarctic" in link.lower() or "iceberg" in link.lower():
                best_link = link
                break
                
        if not best_link:
            best_link = csv_links[0]
            
        filepath, filename = download_file(best_link)
        if filepath:
            return f"Success! Downloaded latest report: {filename}", filepath, filename
        else:
            return "Scraped URL found, but download process failed due to network timeout.", None, None
            
    except Exception as e:
        # Format user friendly error logs
        error_msg = str(e)
        print(f"USNIC Scraping error: {error_msg}")
        
        # High-utility Fallback: Community dataset S3 integration
        print("Attempting fallback to community S3 aggregated historical dataset...")
        fallback_url = "https://usi-icebergs.s3.eu-central-1.amazonaws.com/icebergs_locations_usi.csv"
        try:
            filepath, filename = download_file(fallback_url)
            if filepath:
                return f"USNIC down. Successfully recovered using fallback aggregated S3 dataset: {filename}", filepath, filename
        except Exception as fallback_err:
            print(f"Fallback download also failed: {fallback_err}")
            
        return f"Synchronization failed: Could not connect to USNIC servers ({error_msg})", None, None
