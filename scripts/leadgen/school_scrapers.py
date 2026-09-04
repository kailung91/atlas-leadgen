"""
Senior-Level Production Scraper Engine for Ukrainian School Portals & KVED Datasets.
Sources:
  1. znayshov.com (Direct parsing of school details: name, email, phone, director, address)
  2. osvita.ua (JS-obfuscation decoding for emails, address, phone)
  3. ua-region.com.ua (Official KVED 85.31, 85.20, 85.10, 85.32, 85.41, 85.59, 85.60 dataset)
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Generator

import bs4
import pandas as pd
import requests
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "raw" / "school_leads"
DATA_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_REGEX = re.compile(r'\(?\d{3,5}\)?\s*[\d\-]{5,9}')

OBLASTS = {
    "10874": "М.КИЇВ",
    "24517": "КИЇВСЬКА ОБЛАСТЬ",
    "14865": "ЛЬВІВСЬКА ОБЛАСТЬ",
    "5300": "ОДЕСЬКА ОБЛАСТЬ",
    "2266": "ХАРКІВСЬКА ОБЛАСТЬ",
    "36358": "ДНІПРОПЕТРОВСЬКА ОБЛАСТЬ",
    "7922": "ВІННИЦЬКА ОБЛАСТЬ",
    "11956": "ЧЕРКАСЬКА ОБЛАСТЬ",
    "17081": "ІВАНО-ФРАНКІВСЬКА ОБЛАСТЬ",
    "19612": "ЖИТОМИРСЬКА ОБЛАСТЬ",
    "20519": "ЧЕРНІВЕЦЬКА ОБЛАСТЬ",
    "21643": "ВОЛИНСЬКА ОБЛАСТЬ",
    "23026": "ПОЛТАВСЬКА ОБЛАСТЬ",
    "28158": "ХМЕЛЬНИЦЬКА ОБЛАСТЬ",
    "32404": "ЧЕРНІГІВСЬКА ОБЛАСТЬ",
    "33349": "ТЕРНОПІЛЬСЬКА ОБЛАСТЬ",
    "35147": "ЗАКАРПАТСЬКА ОБЛАСТЬ",
    "37839": "МИКОЛАЇВСЬКА ОБЛАСТЬ",
    "39095": "КІРОВОГРАДСЬКА ОБЛАСТЬ",
    "40151": "РІВНЕНСЬКА ОБЛАСТЬ",
    "41708": "ЗАПОРІЗЬКА ОБЛАСТЬ",
    "16168": "СУМСЬКА ОБЛАСТЬ",
    "19000": "ХЕРСОНСЬКА ОБЛАСТЬ",
    "3431": "ДОНЕЦЬКА ОБЛАСТЬ",
    "6259": "ЛУГАНСЬКА ОБЛАСТЬ",
}


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' "\t\r\n')


def extract_city_from_address(address: str) -> str:
    if not address:
        return ""
    m = re.search(r'\b(?:м\.|місто|с\.|смт\.?|селище)\s*([А-ЯІЇЄҐа-яіїєґ\'\-]+)', address)
    if m:
        return m.group(1)
    parts = [p.strip() for p in address.split(",")]
    return parts[0] if parts else ""


class ZnayshovParser:
    """Production parser for znayshov.com school detail pages."""

    @staticmethod
    def parse_page(url: str, html: bytes | str) -> dict[str, str] | None:
        soup = bs4.BeautifulSoup(html, "html.parser")
        
        h2 = soup.find("h2", class_="text-center")
        short_name = clean_text(h2.text) if h2 else ""
        
        h3 = soup.find("h3", class_="text-center")
        full_name = clean_text(h3.text) if h3 else ""
        
        name = full_name or short_name
        if not name:
            return None
            
        card_blue = [c for c in soup.find_all("div", class_="znv-card-blue") if "Контакти" in c.text]
        card_text = card_blue[0].text if card_blue else ""
        
        email_match = EMAIL_REGEX.search(card_text)
        email = email_match.group(0).lower() if email_match else ""
        
        phone_match = PHONE_REGEX.search(card_text)
        phone = phone_match.group(0) if phone_match else ""
        
        director = ""
        if "Директор" in card_text:
            after_dir = card_text.split("Директор")[-1]
            for stopper in ["Ел.почта", "Телефон", "Індекс", "КОАТУУ"]:
                if stopper in after_dir:
                    after_dir = after_dir.split(stopper)[0]
            director = clean_text(after_dir)
            
        address = ""
        card_gray = [c for c in soup.find_all("div", class_="znv-card-gray") if "Адреса" in c.text]
        if card_gray:
            raw_addr = card_gray[0].text.replace("Адреса", "").split("Гугл Карта")[0]
            address = clean_text(raw_addr)
            
        city = extract_city_from_address(address)
        
        return {
            "source": "znayshov.com",
            "url": url,
            "name": name,
            "short_name": short_name,
            "email": email,
            "phone": phone,
            "director": director,
            "city": city,
            "address": address,
        }


class OsvitaUaParser:
    """Production parser for osvita.ua school pages (with JS unescape decoding)."""

    @staticmethod
    def parse_page(url: str, html: bytes | str) -> dict[str, str] | None:
        soup = bs4.BeautifulSoup(html, "html.parser")
        
        h1 = soup.find("h1", class_="text-header-title")
        name = clean_text(h1.text) if h1 else ""
        if not name or "Школи України" in name:
            return None
            
        email = ""
        for script in soup.find_all("script"):
            stext = script.string or script.text or ""
            if "%" in stext:
                decoded = urllib.parse.unquote(stext)
                em = EMAIL_REGEX.search(decoded)
                if em:
                    email = em.group(0).lower()
                    break
                    
        address, phone = "", ""
        container = soup.find("div", class_="block-frame-2167")
        if container:
            spans = container.find_all("span", class_="telefon")
            if len(spans) >= 1:
                address = clean_text(spans[0].text)
            if len(spans) >= 2:
                phone = clean_text(spans[1].text)
                
        city = extract_city_from_address(address)
        
        return {
            "source": "osvita.ua",
            "url": url,
            "name": name,
            "short_name": name,
            "email": email,
            "phone": phone,
            "director": "",
            "city": city,
            "address": address,
        }


def test_parsers_standalone():
    session = requests.Session()
    session.headers.update({"User-Agent": random.choice(USER_AGENTS)})
    
    r_z = session.get("https://znayshov.com/Schools/Details/odeska_oblast_m.odesa/_ananivskyi_litsei_2_/12251", timeout=15)
    rec_z = ZnayshovParser.parse_page(r_z.url, r_z.content)
    logger.info("Znayshov parser output: {}", rec_z)
    assert rec_z and rec_z["email"] == "anlicey2@gmail.com", "Znayshov email mismatch"

    r_o = session.get("https://osvita.ua/school/school-ukraine/37198/", timeout=15)
    rec_o = OsvitaUaParser.parse_page(r_o.url, r_o.content)
    logger.info("Osvita parser output: {}", rec_o)
    assert rec_o and rec_o["email"] == "school@brobots.org.ua", "Osvita email mismatch"
    
    print("✅ ALL SENIOR PARSER ENGINE TESTS PASSED!")


if __name__ == "__main__":
    test_parsers_standalone()
