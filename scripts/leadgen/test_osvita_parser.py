import bs4
import requests
import re

url = "https://osvita.ua/school/school-ukraine/37198/"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
soup = bs4.BeautifulSoup(r.content, "html.parser")

h1 = soup.find("h1", class_="text-header-title")
name = h1.text.strip() if h1 else ""

phone_span = soup.find("span", class_="telefon")
phone = phone_span.text.strip() if phone_span else ""

# Email & Website from links or container text
links = [a["href"] for a in soup.find_all("a", href=True)]
email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', soup.text)
email = email_match.group(0).lower() if email_match else ""

web = ""
for a in soup.find_all("a", href=True):
    href = a["href"]
    if href.startswith("http") and "osvita.ua" not in href and "facebook" not in href:
        web = href
        break

print("Osvita School Name:", name)
print("Phone:", phone)
print("Email:", email)
print("Website:", web)
