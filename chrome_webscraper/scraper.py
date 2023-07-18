# Remember that while web scraping can be a powerful tool,
# it's important to always respect the terms of service of the website you're scraping,
# as well as the laws and regulations applicable to your area.
# NOTE: There are some open-source Docker files for this
# https://github.com/joyzoursky/docker-python-chromedriver/blob/master/py-alpine/3.10-alpine-selenium/Dockerfile
import pprint

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from chrome_webscraper.extract_profile import extract_profile_data, text_from_html
from common.openai_client import OpenAiClient

pp = pprint.PrettyPrinter(indent=2)

# Create a new instance of the Google Chrome driver
chrome_options = Options()
# five seconds def enough for local, might be worth to get a huge ass machine for production
CHROME_OPTIONS_DEFAULT_WAIT_TIME = 5
chrome_options.add_argument("--no-sandbox")
# For Docker (or when annoying on local)
# chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

# Create the Chrome driver
driver = webdriver.Chrome(
    executable_path="/usr/local/bin/chromedriver",
    service_log_path="chromedriver.log",
    options=chrome_options,
)


# Go to Google's search page
driver.get("https://www.google.com")

# Find the search box, clear it, type in a search and submit it
search_box = driver.find_element_by_name("q")
search_box.clear()
# search_box.send_keys('Peter Csiba Software Engineer LinkedIn')
search_box.send_keys("Martin Stuebler BioFluff")
search_box.submit()

# DynamoDB is used for caching between local test runs, spares both time and money!
open_ai_client = OpenAiClient()

try:
    # Wait until the first search result is loaded
    wait = WebDriverWait(driver, int(CHROME_OPTIONS_DEFAULT_WAIT_TIME))
    first_result = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.g a"))
    )

    # Find the first LinkedIn link
    # Please note that automating LinkedIn is against their policy and can lead to account suspension.
    linkedin_results = [
        result
        for result in driver.find_elements_by_css_selector("div.g a")
        if "linkedin.com" in result.get_attribute("href")
    ]

    # If we have any LinkedIn results, navigate to the first one
    if linkedin_results:
        linkedin_results[0].click()
        profile_url = driver.current_url

        try:
            # Wait for the dismissal button to appear and then click it
            # dismiss_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".modal__dismiss")))
            dismiss_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".modal__dismiss"))
            )
            dismiss_button.click()

            # Wait until the LinkedIn profile page is fully rendered
            # Here we're waiting for the presence of the element that contains the profile name
            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".top-card-layout__title")
                )
            )
        except TimeoutException:
            # NOT ideal, but there is a good chance most of the relevant content is there as the behavior ain't 100%.
            print("Timed out waiting for dismissal button to load")

        # Now we are on the profile page and can parse it with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Save the content to a local file
        filename = "output.html"
        with open(filename, "w") as f:
            # profile_data = parse_profile_data(soup)
            # print(f"profile_data: {profile_data}")
            text_content = text_from_html(soup)
            profile_data = extract_profile_data(open_ai_client, text_content)
            pp.pprint(profile_data)

            content = str(soup.prettify())
            print(f"storing {len(content)}B into {filename} from url {profile_url}")
            f.write(content)

except TimeoutException:
    print("Timed out waiting for page to load")
finally:
    # Close the browser
    driver.quit()
