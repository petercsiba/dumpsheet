import json
import pickle
import pprint
import os
import time

from linkedin_scraper import Person, actions
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

email = "petherz@gmail.com"
password = "PASSWORD"
output_folder = "data"
SCRAPED_OUTPUT = f"{output_folder}/scraped_data.json"
pp = pprint.PrettyPrinter(indent=4)

driver = webdriver.Chrome()
# if email and password isn't given, it'll prompt in terminal
actions.login(driver, email, password)

def get_all_my_contacts():
    driver.get("https://www.linkedin.com/mynetwork/invite-connect/connections/")
    # 5 second timeout
    _ = WebDriverWait(driver, 5).until(
        EC.presence_of_element_located((By.CLASS_NAME, "mn-connections"))
    )
    # TODO(peter): Here we need to figure out a way to get everyone
    #   Need to click on "Load More" and then keep scrolling
    # Use sth like
    # <span class="artdeco-button__text">
    #     Show more results
    # </span>
    #     def mouse_click(self, elem):
    #         action = webdriver.ActionChains(self.driver)
    #         action.move_to_element(elem).perform()
    # _ = WebDriverWait(driver, self.__WAIT_FOR_ELEMENT_TIMEOUT).until(
    #      EC.presence_of_element_located(
    #          (
    #              By.XPATH,
    #              "//*[@class='pv-profile-section pv-interests-section artdeco-container-card artdeco-card ember-view']",
    #          )
    #      )
    #  )
    #  interestContainer = driver.find_element(By.XPATH,
    #      "//*[@class='pv-profile-section pv-interests-section artdeco-container-card artdeco-card ember-view']"
    #  )
    connections = driver.find_element(By.CLASS_NAME, "mn-connections")

    results = []
    if connections is not None:
        for conn in connections.find_elements(By.CLASS_NAME, "mn-connection-card"):
            anchor = conn.find_element(By.CLASS_NAME, "mn-connection-card__link")
            url = anchor.get_attribute("href")
            name = (
                conn.find_element(By.CLASS_NAME, "mn-connection-card__details")
                .find_element(By.CLASS_NAME, "mn-connection-card__name")
                .text.strip()
            )
            occupation = (
                conn.find_element(By.CLASS_NAME, "mn-connection-card__details")
                .find_element(By.CLASS_NAME, "mn-connection-card__occupation")
                .text.strip()
            )
            results.append(
                {
                    "name": name,
                    "occupation": occupation,
                    "url": url,
                }
            )
    return results


# Shamelessly copied from https://github.com/joeyism/linkedin_scraper/blob/master/linkedin_scraper/person.py#L255
# - the idea of the package is great, but the usability can be improved.
def get_person(linkedin_url):
    their_person = Person(linkedin_url, driver=driver, scrape=False, close_on_complete=False)

    WebDriverWait(driver, 5).until(
        EC.presence_of_element_located(
            (
                By.CLASS_NAME,
                "pv-top-card",
            )
        )
    )
    driver.execute_script('alert("Focus window")')
    driver.switch_to.alert.accept()
    print("Sleeping 5 seconds")
    time.sleep(5)

    their_person.get_name_and_location()
    their_person.open_to_work = their_person.is_open_to_work()

    # get about
    their_person.get_about()
    driver.execute_script(
        "window.scrollTo(0, Math.ceil(document.body.scrollHeight/2));"
    )
    driver.execute_script(
        "window.scrollTo(0, Math.ceil(document.body.scrollHeight/1.5));"
    )
    # get the rest
    their_person.get_experiences()
    their_person.get_educations()

    experiences = []
    for their_exp in their_person.experiences:
        exp = vars(their_exp)
        if "description" in exp and not isinstance(exp["description"], str):
            # This can happen: 'description': <selenium.webdriver.remote.webelement.WebElement (session=...
            exp["description"] = None
        experiences.append(exp)

    # their_person is hard to work with, it has a __repr__ overload AND it can NOT be pickled so translate to json
    return {
        "linkedin_url": their_person.linkedin_url,
        "name": their_person.name,
        "about": their_person.about,
        "experiences": experiences,
        "educations": [vars(edu) for edu in their_person.educations],
        # "interests": their_person.interests,
        # "accomplishments": their_person.accomplishments,
        # "also_viewed_urls": their_person.also_viewed_urls,
        # contacts is fake new
    }


def mkdir_safe(directory_name):
    if not os.path.exists(directory_name):
        os.makedirs(directory_name)


# load previously scraped data
if os.path.exists(SCRAPED_OUTPUT):
    print(f"Loading {SCRAPED_OUTPUT}")
    with open(SCRAPED_OUTPUT, "r") as handle:
        data = json.load(handle)
    urls = data.keys()
else:
    data = {}
    contacts = get_all_my_contacts()
    urls = [c["url"] for c in contacts]
    # So the url itself gets dumped (and can be loaded later)
    for url in urls:
        data[url] = None

sum_empty = sum(data[url] is None for url in data.keys())
print(f"Will attempt on scrape {sum_empty} / {len(data)} connections")

# keep scraping
for url in urls:
    if url in data and data[url] is not None:
        print(f"Skipping {url}")
        continue

    print(f"Downloading {url}")
    try:
        person = get_person(url)
    except Exception as ex:
        print(f"exception occurred skipping person: {ex}")
        continue

    pp.pprint(person)

    # print(person)
    data[url] = person
    mkdir_safe(output_folder)
    filename = url.replace("https://www.linkedin.com/in/", "").replace("/", "").strip() + ".json"
    # filename = f"{''.join(person.name.split())}.pickle"
    with open(f"{output_folder}/{filename}", "w") as handle:
        json.dump(person, handle)

    print(f"Sleeping for 15 seconds - saved to {filename}")
    time.sleep(15)

# save scraped data
print("Saving scraped data")
with open(SCRAPED_OUTPUT, 'w') as handle:
    json.dump(data, handle)  # protocol=pickle.HIGHEST_PROTOCOL

driver.close()
