"""
Merton Council Bin Collection Scraper

FINAL CORRECT SOLUTION:
The FixMyStreet platform (https://fixmystreet.merton.gov.uk) provides a
direct iCalendar (.ics) feed. All Selenium/HTML scraping
approaches are incorrect as the site uses anti-bot measures.

This script now implements the true fix by:
1.  Taking the base waste URL (e.g., .../waste/4259013).
2.  Appending '/calendar.ics' to get the direct data feed.
3.  Completely removing Selenium and using 'requests'.
4.  Parsing the .ics file to extract collection dates.
"""
import requests
from datetime import datetime
from ics import Calendar

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CouncilClass(AbstractGetBinDataClass):
    """
    Concrete class for Merton Council bin collection scraper.
    Uses Requests and the 'ics' library to parse the direct iCalendar feed.
    """

    def parse_data(self, page: str, **kwargs) -> dict:
        
        # 1. Get the base URL from the page argument
        url_str = str(page) if hasattr(page, '__str__') else page
        if hasattr(page, 'url'):
            url_str = page.url
        
        # 2. Append /calendar.ics to get the direct feed URL
        # e.g., https://fixmystreet.merton.gov.uk/waste/4259013/calendar.ics
        calendar_url = f"{url_str.rstrip('/')}/calendar.ics"
        
        # 3. Download the .ics file
        try:
            response = requests.get(calendar_url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()  # Check for HTTP errors
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error fetching ICS calendar from {calendar_url}: {e}")

        # 4. Parse the calendar
        try:
            calendar = Calendar(response.text)
        except Exception as e:
            raise Exception(f"Error parsing ICS file: {e}")

        data = {"bins": []}
        today = datetime.now().date()

        # 5. Extract events
        for event in calendar.events:
            # Only include events from today onwards
            if event.begin.date() >= today:
                # Clean up the summary name (e.g., "Food waste collection" -> "Food waste")
                bin_type = event.name.replace(" collection", "").strip()
                
                # Format the date
                collection_date = event.begin.strftime(date_format)
                
                data["bins"].append({
                    "type": bin_type,
                    "collectionDate": collection_date
                })

        if not data["bins"]:
            raise Exception("ICS calendar was parsed but no upcoming events were found.")
        
        # Sort by collection date
        data["bins"].sort(key=lambda x: datetime.strptime(x["collectionDate"], date_format))
        
        return data
