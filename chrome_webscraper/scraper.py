# Remember that while web scraping can be a powerful tool,
# it's important to always respect the terms of service of the website you're scraping,
# as well as the laws and regulations applicable to your area.
# NOTE: There are some open-source Docker files for this
# https://github.com/joyzoursky/docker-python-chromedriver/blob/master/py-alpine/3.10-alpine-selenium/Dockerfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# Create a new instance of the Google Chrome driver
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument("--headless")
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument("--window-size=1920,1080")
# driver = webdriver.Chrome(chrome_options=options)
driver = webdriver.Chrome(executable_path='/usr/bin/chromedriver', options=chrome_options)

# Go to Google's search page
driver.get("https://www.google.com")

# Find the search box, clear it, type in a search and submit it
search_box = driver.find_element_by_name('q')
search_box.clear()
search_box.send_keys('Peter Csiba Software Engineer LinkedIn')
search_box.submit()

try:
    # Wait until the first search result is loaded
    wait = WebDriverWait(driver, int(15))
    first_result = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.g a")))

    # Find the first LinkedIn link
    linkedin_results = [result for result in driver.find_elements_by_css_selector('div.g a') if 'linkedin.com' in result.get_attribute('href')]

    # If we have any LinkedIn results, navigate to the first one
    if linkedin_results:
        linkedin_results[0].click()

        # Wait until the LinkedIn profile page is fully rendered
        # Here we're waiting for the presence of the element that contains the profile picture (as an example)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".pv-top-card__photo")))

        # Now we are on the profile page and can parse it with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Save the content to a local file
        with open("output.html", "w") as f:
            f.write(str(soup.prettify()))

except TimeoutException:
    print("Timed out waiting for page to load")

# Close the browser
driver.quit()
