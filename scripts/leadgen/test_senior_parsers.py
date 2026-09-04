"""
Senior-level Parser & Validation Unit Test for School Portals
"""
import urllib.parse
import re
import bs4
import requests

def test_znayshov_parser():
    url = "https://znayshov.com/Schools/Details/odeska_oblast_m.odesa/_ananivskyi_litsei_2_/12251"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    assert r.status_code == 200, f"Status code: {r.status_code}"
    
    soup = bs4.BeautifulSoup(r.content, "html.parser")
    
    # 1. Short name
    h2 = soup.find("h2", class_="text-center")
    short_name = h2.text.strip(' "\t\r\n') if h2 else ""
    
    # 2. Full official name
    h3 = soup.find("h3", class_="text-center")
    full_name = h3.text.strip(' "\t\r\n') if h3 else ""
    
    # 3. Contacts container
    card_blue = [c for c in soup.find_all("div", class_="znv-card-blue") if "Контакти" in c.text]
    card_text = card_blue[0].text if card_blue else ""
    
    # 4. Email (ASCII only pattern)
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', card_text)
    email = email_match.group(0).lower() if email_match else ""
    
    # 5. Phone
    phone_match = re.search(r'\(?\d{3,5}\)?\s*[\d\-]{5,9}', card_text)
    phone = phone_match.group(0) if phone_match else ""
    
    # 6. Director
    director = ""
    if "Директор" in card_text:
        after_dir = card_text.split("Директор")[-1]
        for stopper in ["Ел.почта", "Телефон", "Індекс", "КОАТУУ"]:
            if stopper in after_dir:
                after_dir = after_dir.split(stopper)[0]
        director = after_dir.strip()
        
    print("[ZNAYSHOV TEST RESULT]")
    print(f"  Short Name : {short_name}")
    print(f"  Full Name  : {full_name}")
    print(f"  Email      : {email}")
    print(f"  Phone      : {phone}")
    print(f"  Director   : {director}")
    
    assert short_name == "Ананьївський ліцей №2", f"Unexpected short_name: {short_name}"
    assert email == "anlicey2@gmail.com", f"Unexpected email: {email}"
    assert phone == "(04863)21564", f"Unexpected phone: {phone}"
    assert director == "Колойденко Михайло Васильович", f"Unexpected director: {director}"
    print("✅ Znayshov Parser Test PASSED!")


def test_osvita_parser():
    url = "https://osvita.ua/school/school-ukraine/37198/"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers)
    assert r.status_code == 200, f"Status code: {r.status_code}"
    
    soup = bs4.BeautifulSoup(r.content, "html.parser")
    
    # 1. School Title
    h1 = soup.find("h1", class_="text-header-title")
    name = h1.text.strip() if h1 else ""
    
    # 2. Email (handling JS eval(unescape(...)))
    email = ""
    for script in soup.find_all("script"):
        stext = script.string or script.text or ""
        if "%" in stext:
            decoded = urllib.parse.unquote(stext)
            em = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', decoded)
            if em:
                email = em.group(0).lower()
                break
                    
    # 3. Address & Phone from block-frame-2167
    address, phone = "", ""
    container = soup.find("div", class_="block-frame-2167")
    if container:
        spans = container.find_all("span", class_="telefon")
        if len(spans) >= 1:
            address = spans[0].text.strip()
        if len(spans) >= 2:
            phone = spans[1].text.strip()
            
    print("\n[OSVITA.UA TEST RESULT]")
    print(f"  Name    : {name}")
    print(f"  Email   : {email}")
    print(f"  Phone   : {phone}")
    print(f"  Address : {address}")
    
    assert name == "#brobots, інжинірингова школа", f"Unexpected name: {name}"
    assert email == "school@brobots.org.ua", f"Unexpected email: {email}"
    assert phone == "(063) 450-88-01‬", f"Unexpected phone: {phone}"
    print("✅ Osvita.ua Parser Test PASSED!")


if __name__ == "__main__":
    test_znayshov_parser()
    test_osvita_parser()
