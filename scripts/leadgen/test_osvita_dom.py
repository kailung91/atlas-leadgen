import bs4
import requests

url = "https://osvita.ua/school/school-ukraine/37198/"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
r = requests.get(url, headers=headers)
soup = bs4.BeautifulSoup(r.content, "html.parser")

container = soup.find("div", class_="block-frame-2178") or soup.find("div", class_="tbl-700")
print("Container HTML:")
if container:
    print(container.prettify())
