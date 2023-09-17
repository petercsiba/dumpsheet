import plistlib

from bs4 import BeautifulSoup

FILE = "linkedin-contacts.webarchive"
# Load the webarchive file
with open(f"/Users/petercsiba/Desktop/{FILE}", "rb") as f:
    webarchive = plistlib.load(f)

# Extract the main resource (this is typically the main HTML)
main_resource = webarchive["WebMainResource"]
html_data = main_resource["WebResourceData"]

soup = BeautifulSoup(html_data, "html.parser")

# If you want to save the extracted HTML:
with open(f"/Users/petercsiba/Downloads/{FILE}.html", "w", encoding="utf-8") as out:
    out.write(soup.prettify())

# Find all 'a' tags with hrefs that match the pattern '/in/{something}'
matching_links = soup.find_all(
    "a", href=lambda href: (href is not None and href.startswith("/in/"))
)

# Extract href values from the matching links
urls = list(set([link["href"] for link in matching_links]))
urls = [f"https://www.linkedin.com{u}" for u in urls]
print(f"Total {len(urls)} connections found")

for url in urls[:10]:
    print(url)
