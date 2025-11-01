"""
Updated Merton Council Bin Collection Scraper
URL changed from myneighbourhood.merton.gov.uk to fixmystreet.merton.gov.uk/waste
"""
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from datetime import datetime

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CouncilClass(AbstractGetBinDataClass):
    """
    Concrete class for Merton Council bin collection scraper.
    Now uses Selenium due to JavaScript-driven form on new FixMyStreet platform.
    """

    def parse_data(self, page: str, **kwargs) -> dict:
        # Extract postcode from kwargs or URL
        user_postcode = kwargs.get("postcode")
        user_uprn = kwargs.get("uprn")
        
        if not user_postcode and not user_uprn:
            raise ValueError("Postcode or UPRN is required for Merton Council")

        # Set up Selenium WebDriver
        driver = None
        page_source = None
        
        try:
            driver = create_webdriver()
            driver.get("https://fixmystreet.merton.gov.uk/waste")
            
            # Wait for and find the postcode input field
            wait = WebDriverWait(driver, 15)
            
            try:
                postcode_input = wait.until(
                    EC.presence_of_element_located((By.ID, "pc"))
                )
            except TimeoutException:
                raise Exception("Could not load Merton waste collection page - postcode input not found")
            
            # Enter postcode
            postcode_input.clear()
            postcode_input.send_keys(user_postcode if user_postcode else user_uprn)
            
            # Click the submit button
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
                submit_button.click()
            except Exception as e:
                raise Exception(f"Could not submit postcode form: {e}")
            
            # Wait for address selection or results page
            try:
                # Check if address selector appears (multiple addresses for postcode)
                from selenium.webdriver.support.ui import Select
                address_select = wait.until(
                    EC.presence_of_element_located((By.ID, "address"))
                )
                
                # Select first address option (skip the placeholder)
                select = Select(address_select)
                if len(select.options) > 1:
                    select.select_by_index(1)  # Select first real address
                else:
                    raise Exception(f"No addresses found for postcode {user_postcode}")
                
                # Click go button
                go_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
                go_button.click()
                
            except TimeoutException:
                # No address selector, might have gone straight to results
                pass
            
            # Wait for collection schedule to load
            try:
                wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".waste-service, .collection-item, [class*='waste'], [class*='collection']"))
                )
            except TimeoutException:
                raise Exception("Collection schedule did not load - no collection data found on page")
            
            # Get the page source for parsing
            page_source = driver.page_source
            
        except Exception as e:
            # Re-raise with context
            raise Exception(f"Selenium scraping failed for Merton Council: {e}")
            
        finally:
            if driver:
                driver.quit()
        
        if not page_source:
            raise Exception("Failed to retrieve page content")
        
        # Parse the results page
        soup = BeautifulSoup(page_source, "html.parser")
        data = {"bins": []}
        
        # Try multiple possible container class names (site structure may vary)
        waste_services = (
            soup.find_all("div", class_="waste-service") or
            soup.find_all("section", class_="waste-service") or
            soup.find_all("div", class_=lambda x: x and "waste" in x.lower()) or
            soup.find_all("div", class_=lambda x: x and "collection" in x.lower())
        )
        
        if not waste_services:
            raise Exception("Could not find waste service containers on results page")
        
        possible_date_formats = [
            "%A %d %B %Y",     # "Friday 24 October 2025"
            "%A %d %B",        # "Friday 24 October"
            "%d %B %Y",        # "24 October 2025"
            "%d %B",           # "24 October"
            "%d/%m/%Y",        # "24/10/2025"
            "%d-%m-%Y",        # "24-10-2025"
        ]
        
        current_year = datetime.now().year
        
        for service in waste_services:
            try:
                # Extract bin type from heading (try multiple tag types)
                heading = service.find(["h2", "h3", "h4", "strong"])
                if not heading:
                    # Try finding by class
                    heading = service.find(class_=lambda x: x and any(term in x.lower() for term in ["title", "name", "type"]))
                
                if not heading:
                    continue
                    
                bin_type = heading.get_text(strip=True)
                
                # Skip empty bin types
                if not bin_type or bin_type.lower() in ["", " "]:
                    continue
                
                # Find the "Next collection" date
                next_collection_date = None
                
                # Look for paragraphs, divs, or definition lists containing collection info
                info_elements = service.find_all(["p", "div", "dd", "dt", "span", "li"])
                
                for element in info_elements:
                    text = element.get_text()
                    text_lower = text.lower()
                    
                    if "next collection" in text_lower:
                        # Extract date from the text
                        date_text = None
                        
                        if ":" in text:
                            # Date after colon: "Next collection: Friday 24 October"
                            date_text = text.split(":", 1)[1].strip()
                        else:
                            # Look for bold tags
                            bold = element.find(["b", "strong"])
                            if bold:
                                date_text = bold.get_text(strip=True)
                            else:
                                # Remove "Next collection" text
                                date_text = text.replace("Next collection", "").replace("next collection", "").strip()
                        
                        # Clean up common prefixes
                        for prefix in ["on ", "is ", "date "]:
                            if date_text and date_text.lower().startswith(prefix):
                                date_text = date_text[len(prefix):].strip()
                        
                        if date_text and len(date_text) > 3:
                            # Try parsing with different formats
                            for fmt in possible_date_formats:
                                try:
                                    parsed_date = datetime.strptime(date_text, fmt)
                                    
                                    # If year not in format, use current or next year
                                    if "%Y" not in fmt:
                                        parsed_date = parsed_date.replace(year=current_year)
                                        
                                        # If date is in the past, assume next year
                                        if parsed_date < datetime.now():
                                            parsed_date = parsed_date.replace(year=current_year + 1)
                                    
                                    next_collection_date = parsed_date
                                    break
                                    
                                except ValueError:
                                    continue
                        
                        if next_collection_date:
                            break
                
                # Add to data if we found a valid date
                if next_collection_date:
                    dict_data = {
                        "type": bin_type,
                        "collectionDate": next_collection_date.strftime(date_format),
                    }
                    data["bins"].append(dict_data)
                    
            except Exception as e:
                # Log but don't fail entire scrape if one bin fails
                print(f"Warning: Failed to parse bin service: {e}")
                continue
        
        if not data["bins"]:
            raise Exception("No collection dates found - page structure may have changed")
        
        # Sort by collection date
        try:
            data["bins"].sort(key=lambda x: datetime.strptime(x["collectionDate"], date_format))
        except Exception:
            # If sorting fails, return unsorted
            pass
        
        return data
