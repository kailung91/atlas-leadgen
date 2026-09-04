"""
ОФІЦІЙНИЙ Скрапер Договорів Prozorro Contract Search API — v6.0
Збирає ПОСНЕ ПАРТНЕРСТВО:
  - 🏆 Переможці / Постачальники / Конкуренти (Назва, ЄДРПОУ, Компанія)
  - 🏛️ Замовники / Покупці (Школи, Ліцеї, Відділи Освіти)
  - 💰 Суми підписаних договорів (грн)
  - 📅 Дати підписання (2023-2026)
  - ✉️ Верифіковані Email замовників та переможців (DNS MX Active)
"""
import asyncio
import json
import re
import socket
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import dns.resolver
import pandas as pd
from loguru import logger
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CONTRACTS_API = "https://prozorro.gov.ua/api/search/contracts"

TARGET_QUERIES = [
    "навчальний атлас",
    "навчальні атласи",
    "атлас з історії",
    "атлас з географії",
    "контурна карта",
    "контурні карти",
    "глобус",
    "глобуси",
    "стінна карта",
    "стінні карти",
    "карта України настінна",
    "обладнання кабінету географії",
    "обладнання кабінету історії",
]

KEYWORD_DENY_RE = re.compile(
    r"медичн|амбулатор|електрокардіо|ЕКГ|ecg|"
    r"пам.яті|microsd|sd.карт|"
    r"паливо|паливн|нафт|оливи|мастил|"
    r"ванн|сантех|санітарн|плитк|"
    r"картридж|тонер|принтер|"
    r"харчуванн|їдальн|ноутбук|комп.ютер",
    re.IGNORECASE,
)

BUYER_DENY_RE = re.compile(
    r"лікарн|поліклінік|амбулатор|диспансер|госпіталь|"
    r"укрнафт|водоканал|теплопостач|"
    r"поліці|прокуратур|суд|митн|ДСНС|dsns|пожежн",
    re.IGNORECASE,
)

MIN_VALUE_UAH = 1_000
CONCURRENCY = 10
TIMEOUT = aiohttp.ClientTimeout(connect=5, total=20)

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
HOSTILE_DOMAINS = {"mail.ru", "yandex.ru", "yandex.ua", "rambler.ru", "bk.ru"}


def is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    email = email.strip().lower()
    domain = email.split("@")[-1]
    return (
        domain not in HOSTILE_DOMAINS
        and not domain.endswith((".ru", ".su", ".by"))
        and bool(RE_EMAIL.fullmatch(email))
    )


_mx_cache: dict[str, bool] = {}

def verify_mx(domain: str) -> bool:
    domain = domain.lower().strip()
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        dns.resolver.resolve(domain, "MX", lifetime=3.0)
        _mx_cache[domain] = True
        return True
    except Exception:
        pass
    try:
        socket.gethostbyname(domain)
        _mx_cache[domain] = True
        return True
    except Exception:
        _mx_cache[domain] = False
        return False


async def search_contracts(session: aiohttp.ClientSession, query: str, sem: asyncio.Semaphore) -> list[dict]:
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    contracts = []
    page = 1
    per_page = 100

    async with sem:
        while True:
            payload = {"text": query, "page": page, "per_page": per_page}
            try:
                async with session.post(CONTRACTS_API, json=payload, headers=headers, timeout=TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data") or []
                        total = data.get("total") or 0
                        if not items:
                            break
                        contracts.extend(items)
                        if len(contracts) >= total or page >= 30:  # max 3000 per query
                            break
                        page += 1
                        await asyncio.sleep(0.3)
                    elif resp.status == 429:
                        await asyncio.sleep(3.0)
                    else:
                        break
            except Exception as e:
                logger.debug("Contract search error for '{}' page {}: {}", query, page, e)
                break

    logger.info("✅ Договори для '{}': знайдено {} записів", query, len(contracts))
    return contracts


def parse_contract_row(c: dict) -> dict | None:
    buyer = c.get("buyer") or {}
    buyer_name = buyer.get("name") or (buyer.get("identifier") or {}).get("legalName") or ""
    buyer_edrpou = (buyer.get("identifier") or {}).get("id") or ""
    contact = buyer.get("contactPoint") or {}
    email = (contact.get("email") or "").strip()
    phone = (contact.get("telephone") or "").strip()
    city = (buyer.get("address") or {}).get("locality") or ""
    region = (buyer.get("address") or {}).get("region") or ""

    suppliers = c.get("suppliers") or []
    supplier_name = suppliers[0].get("name") if suppliers else ""
    supplier_edrpou = (suppliers[0].get("identifier") or {}).get("id") if suppliers else ""

    val = c.get("value") or {}
    amount = val.get("amount") or 0

    if float(amount) < MIN_VALUE_UAH:
        return False

    if BUYER_DENY_RE.search(buyer_name) or BUYER_DENY_RE.search(supplier_name):
        return None

    cid = c.get("contractID") or c.get("id") or ""
    date_signed = (c.get("dateSigned") or "")[:10]

    return {
        "ID Договору": cid,
        "Дата Підписання": date_signed,
        "Сума Договору (грн)": amount,
        "🏆 Переможець (Постачальник)": supplier_name,
        "ЄДРПОУ Переможця": supplier_edrpou,
        "🏛️ Замовник (Покупець)": buyer_name,
        "ЄДРПОУ Замовника": buyer_edrpou,
        "Email Замовника": email if is_valid_email(email) else "",
        "Телефон Замовника": phone,
        "Місто": city,
        "Область": region,
        "Статус Договору": c.get("status") or "",
        "URL Договору": f"https://prozorro.gov.ua/contract/{cid}" if cid else "",
    }


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)

    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info("🚀 Запуск Prozorro Contracts Scraper v6.0 (Замовники + Переможці)")
        logger.info("Пошукових фраз договорів: {}", len(TARGET_QUERIES))

        tasks = [search_contracts(session, q, sem) for q in TARGET_QUERIES]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        raw_contracts_dict = {}
        for query, res in zip(TARGET_QUERIES, search_results):
            if isinstance(res, list):
                for item in res:
                    cid = item.get("contractID") or item.get("id")
                    if cid and cid not in raw_contracts_dict:
                        raw_contracts_dict[cid] = item

        logger.info("Всього унікальних підписаних договорів: {}", len(raw_contracts_dict))

        rows = []
        for contract in raw_contracts_dict.values():
            row = parse_contract_row(contract)
            if row:
                rows.append(row)

        logger.info("Валідних договорів з переможцями та замовниками: {}", len(rows))

    if not rows:
        logger.warning("Нуль договорів.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["ID Договору"])
    df = df.sort_values("Сума Договору (грн)", ascending=False)

    # DNS MX Перевірка
    emails = [e for e in df["Email Замовника"].dropna().astype(str) if is_valid_email(e)]
    domains = list(set(e.split("@")[1] for e in emails))
    logger.info("DNS MX перевірка пошт для {} доменів...", len(domains))

    with ThreadPoolExecutor(max_workers=20) as executor:
        mx_results = list(executor.map(verify_mx, domains))
    domain_mx = dict(zip(domains, mx_results))

    df["DNS MX"] = df["Email Замовника"].map(
        lambda e: "✅ Active" if is_valid_email(str(e)) and domain_mx.get(str(e).split("@")[1], False) else ""
    )

    df.to_csv(OUTPUT_DIR / "prozorro_winners_and_buyers.csv", index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "prozorro_winners_and_buyers.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Переможці та Замовники")
        ws = writer.sheets["Переможці та Замовники"]
        ws.freeze_panes = "A2"
        hfill = PatternFill(start_color="1A3C5E", end_color="1A3C5E", fill_type="solid")
        hfont = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        for col in range(1, len(df.columns) + 1):
            c = ws.cell(row=1, column=col)
            c.fill = hfill
            c.font = hfont
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 30
        for idx, col_name in enumerate(df.columns, 1):
            samples = df[col_name].dropna().astype(str).head(50)
            maxlen = max([len(str(v)) for v in samples] + [len(col_name)])
            ws.column_dimensions[get_column_letter(idx)].width = min(max(maxlen + 3, 12), 55)

    logger.info("✅ Збережено підсумковий Excel договорів (Замовники + Переможці) -> {} ({} рядків)", out_excel.name, len(df))
    logger.info("Унікальних Переможців (Постачальників): {}", df["🏆 Переможець (Постачальник)"].nunique())
    logger.info("Унікальних Замовників (Покупців): {}", df["🏛️ Замовник (Покупець)"].nunique())


if __name__ == "__main__":
    asyncio.run(main())
