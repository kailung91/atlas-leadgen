import bs4
import requests
import re

url = "https://znayshov.com/Schools/Details/odeska_oblast_m.odesa/_ananivskyi_litsei_2_/12251"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
soup = bs4.BeautifulSoup(r.content, "html.parser")

h2 = soup.find("h2", class_="text-center")
short_name = h2.text.strip().strip('"') if h2 else ""

h3 = soup.find("h3", class_="text-center")
full_name = h3.text.strip().strip('"') if h3 else ""

card_blue = [c for c in soup.find_all("div", class_="znv-card-blue") if "Контакти" in c.text]
card_text = card_blue[0].text if card_blue else ""

email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', card_text)
email = email_match.group(0).lower() if email_match else ""

phone_match = re.search(r'\(?\d{3,5}\)?\s*[\d\-]{5,9}', card_text)
phone = phone_match.group(0) if phone_match else ""

director = ""
if "Директор" in card_text:
    after_dir = card_text.split("Директор")[-1]
    for stopper in ["Ел.почта", "Телефон", "Індекс", "КОАТУУ"]:
        if stopper in after_dir:
            after_dir = after_dir.split(stopper)[0]
    director = after_dir.strip()

print("Short Name:", short_name)
print("Full Name:", full_name)
print("Email:", email)
print("Phone:", phone)
print("Director:", director)
