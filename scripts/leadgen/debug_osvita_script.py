import bs4
import requests
import re
import urllib.parse

url = "https://osvita.ua/school/school-ukraine/37198/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
r = requests.get(url, headers=headers)
soup = bs4.BeautifulSoup(r.content, "html.parser")

for i, script in enumerate(soup.find_all("script")):
    stext = script.text or script.string or ""
    if "unescape" in stext or "document.write" in stext or "%" in stext:
        print(f"Script {i}: {stext[:200]}")
        m = re.search(r"unescape\('([^']+)'\)", stext)
        if m:
            print("Found unescape match:", urllib.parse.unquote(m.group(1)))
