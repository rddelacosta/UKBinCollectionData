"""
Merton Council Bin Collection Scraper
Updated for new FixMyStreet platform: https://fixmystreet.merton.gov.uk/waste/{id}
"""
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from datetime import datetime
import time
import re

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CouncilClass(AbstractGetBinDataClass):
    """
    Concrete class for Merton Council bin collection scraper.
    Uses Selenium to handle JavaScript-rendered content.
    """

    def parse_data(self, page: str, **kwargs) -> dict:
        driver = None
        
        try:
            # Configure Chrome for headless operation
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # Use framework's webdriver or create manually
            try:
                driver = create_webdriver()
            except:
                driver = webdriver.Chrome(options=chrome_options)
            
            # Extract URL from page parameter
            url = str(page) if hasattr(page, '__str__') else page
            if hasattr(page, 'url'):
                url = page.url
            
            driver.get(url)
            
            # Wait for JavaScript to load content
            try:
                wait = WebDriverWait(driver, 20)
                wait.until(lambda d: "Food waste" in d.page_source)
            except:
                pass
            
            time.sleep(5)  # Additional wait for dynamic content
            page_source = driver.page_source
                
        finally:
            if driver:
                driver.quit()
        
        # Parse the HTML
        soup = BeautifulSoup(page_source, "html.parser")
        data = {"bins": []}
        
        # Bin types to extract
        bin_types = [
            "Garden Waste",
            "Food waste", 
            "Mixed recycling",
            "Paper and card",
            "Non-recyclable waste"
        ]
        
        current_year = datetime.now().year
        today = datetime.now()
        
        # Date pattern: "Friday 7 November"
        date_pattern = r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)'
        
        # Extract collection dates for each bin type
        for bin_type in bin_types:
            # Find the h3 header containing this bin type
            bin_header = soup.find('h3', text=re.compile(re.escape(bin_type), re.I))
            if not bin_header:
                continue
            
            # Find the next "Next collection" dt element
            next_dt = bin_header.find_next('dt', text=re.compile(r'Next collection', re.I))
            if not next_dt:
                continue
            
            # Get the dd sibling containing the date
            next_dd = next_dt.find_next_sibling('dd')
            if not next_dd:
                continue
            
            # Extract and parse the date
            dd_text = next_dd.get_text(strip=True)
            date_match = re.search(date_pattern, dd_text)
            
            if date_match:
                date_str = date_match.group(0)
                try:
                    parsed_date = datetime.strptime(date_str, "%A %d %B")
                    parsed_date = parsed_date.replace(year=current_year)
                    
                    # Handle year-end rollover (Dec→Jan)
                    if parsed_date < today:
                        parsed_date = parsed_date.replace(year=current_year + 1)
                    
                    # Add to results (avoid duplicates)
                    if not any(b["type"] == bin_type for b in data["bins"]):
                        data["bins"].append({
                            "type": bin_type,
                            "collectionDate": parsed_date.strftime(date_format),
                        })
                except ValueError:
                    continue
        
        if not data["bins"]:
            raise Exception("No collection dates found")
        
        # Sort by collection date
        data["bins"].sort(key=lambda x: datetime.strptime(x["collectionDate"], date_format))
        
        return data
