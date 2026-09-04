"""
DOM Inspector for znayshov.com, osvita.ua, education.ua
"""
import bs4
import requests
from pathlib import Path

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

print("=== 1. ZNAYSHOV.COM ===")
url_z = "https://znayshov.com/Schools/Details/odeska_oblast_m.odesa/_ananivskyi_litsei_2_/12251"
r_z = requests.get(url_z, headers=headers)
soup_z = bs4.BeautifulSoup(r_z.content, "html.parser")

for tag in soup_z.find_all(["h1", "h2", "h3", "h4", "div", "span", "p"]):
    cls = tag.get("class", [])
    t = tag.text.strip()
    if len(t) > 0 and len(t) < 200:
        if any(k in t for k in ["ліцей", "школа", "Директор", "Ел.почта", "Телефон", "Адреса", "66401"]):
            print(f"[{tag.name}.{cls}] -> {t}")

print("\n=== 2. OSVITA.UA ===")
url_o = "https://osvita.ua/school/school-ukraine/37198/"
r_o = requests.get(url_o, headers=headers)
soup_o = bs4.BeautifulSoup(r_o.content, "html.parser")

for tag in soup_o.find_all(["h1", "h2", "h3", "h4", "div", "span", "p"]):
    cls = tag.get("class", [])
    t = tag.text.strip()
    if len(t) > 0 and len(t) < 200:
        if any(k in t for k in ["школа", "Директор", "Телефон", "Адреса", "http", "063"]):
            print(f"[{tag.name}.{cls}] -> {t}")
