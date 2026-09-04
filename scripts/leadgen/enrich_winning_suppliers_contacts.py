"""
ОФІЦІЙНИЙ Скрапер Контактів Переможців Prozorro — v7.0
Збирає ПОВНІ КОНТАКТИ ПЕРЕМОЖЦІВ / КОНКУРЕНТІВ:
  - 🏆 Назва Переможця / Постачальника
  - 🆔 ЄДРПОУ / ІПН Переможця
  - 👤 ПІБ Керівника / Підписанта / Менеджера
  - ✉️ Email Переможця (з верифікацією DNS MX Active)
  - 📞 Телефон Переможця
  - 📍 Юридична адреса, Місто, Область
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

CONTRACTS_SEARCH_API = "https://prozorro.gov.ua/api/search/contracts"
PUBLIC_CONTRACT_API = "https://public.api.openprocurement.org/api/2.5/contracts"

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

CONCURRENCY = 15
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


async def fetch_contract_details(session: aiohttp.ClientSession, guid: str, sem: asyncio.Semaphore) -> dict | None:
    async with sem:
        try:
            url = f"{PUBLIC_CONTRACT_API}/{guid}"
            async with session.get(url, timeout=TIMEOUT) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data")
        except Exception:
            pass
    return None


async def search_contract_guids(session: aiohttp.ClientSession, query: str, sem: asyncio.Semaphore) -> list[str]:
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    guids = []
    page = 1
    per_page = 100

    async with sem:
        while True:
            payload = {"text": query, "page": page, "per_page": per_page}
            try:
                async with session.post(CONTRACTS_SEARCH_API, json=payload, headers=headers, timeout=TIMEOUT) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        items = data.get("data") or []
                        total = data.get("total") or 0
                        if not items:
                            break
                        for item in items:
                            gid = item.get("id")
                            if gid:
                                guids.append(gid)
                        if len(guids) >= total or page >= 20: # max 2000 per query
                            break
                        page += 1
                        await asyncio.sleep(0.1)
                    elif resp.status == 429:
                        await asyncio.sleep(2.0)
                    else:
                        break
            except Exception:
                break

    logger.info("✅ Договори GUIDs для '{}': знайдено {}", query, len(guids))
    return guids


def parse_supplier_contact(contract: dict) -> dict | None:
    suppliers = contract.get("suppliers") or []
    if not suppliers:
        return None

    s = suppliers[0]
    ident = s.get("identifier") or {}
    addr = s.get("address") or {}
    signer = s.get("signerInfo") or {}
    contact = s.get("contactPoint") or {}

    s_name = s.get("name") or ident.get("legalName") or ""
    s_edrpou = ident.get("id") or ""
    
    # ПІБ підписанта/директора
    signer_name = signer.get("name") or contact.get("name") or ""
    
    # Email переможця
    email = (signer.get("email") or contact.get("email") or "").strip().lower()
    
    # Телефон переможця
    phone = (signer.get("telephone") or contact.get("telephone") or "").strip()
    
    # Адреса
    street = addr.get("streetAddress") or ""
    city = addr.get("locality") or ""
    region = addr.get("region") or ""
    full_addr = f"{street}, {city}, {region}".strip(", ")

    if not s_name:
        return None

    cid = contract.get("contractID") or contract.get("id") or ""
    val = contract.get("value") or {}

    return {
        "🏆 Переможець (Назва)": s_name,
        "🆔 ЄДРПОУ / ІПН": s_edrpou,
        "👤 Керівник / Підписант": signer_name,
        "✉️ Email Переможця": email if is_valid_email(email) else "",
        "📞 Телефон Переможця": phone,
        "📍 Місто": city,
        "📍 Область": region,
        "🏠 Юридична Адреса": full_addr,
        "ID Договору": cid,
        "Сума Договору (грн)": val.get("amount") or 0,
        "Дата Підписання": (contract.get("dateSigned") or "")[:10],
    }


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)

    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info("🚀 Збирання контактів Переможців з Public Contract API Prozorro...")

        # 1. Збирання GUIDs договорів
        tasks = [search_contract_guids(session, q, sem) for q in TARGET_QUERIES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_guids = set()
        for res in results:
            if isinstance(res, list):
                all_guids.update(res)

        logger.info("Всього унікальних GUIDs договорів для сканування деталей: {}", len(all_guids))

        # 2. Завантаження деталей договорів з Public API
        guid_list = list(all_guids)
        supplier_records = []
        BATCH = 200

        for i in range(0, len(guid_list), BATCH):
            batch_guids = guid_list[i:i + BATCH]
            detail_tasks = [fetch_contract_details(session, gid, sem) for gid in batch_guids]
            details = await asyncio.gather(*detail_tasks, return_exceptions=True)

            for contract in details:
                if isinstance(contract, dict):
                    row = parse_supplier_contact(contract)
                    if row:
                        supplier_records.append(row)

            logger.info("Завантажено деталей договорів: {}/{} | Витягнуто Переможців: {}", min(i + BATCH, len(guid_list)), len(guid_list), len(supplier_records))

    if not supplier_records:
        logger.warning("Жодного контакту переможця не витягнуто.")
        return

    df_sup = pd.DataFrame(supplier_records)
    
    # Сортуємо та дедуплікуємо за ЄДРПОУ/Назвою (залишаємо найповніші контакти)
    df_sup = df_sup.sort_values(["✉️ Email Переможця", "📞 Телефон Переможця"], ascending=False)
    df_sup = df_sup.drop_duplicates(subset=["🏆 Переможець (Назва)"])

    # Перевірка DNS MX для знайдених пошт переможців
    emails = [e for e in df_sup["✉️ Email Переможця"].dropna().astype(str) if is_valid_email(e)]
    domains = list(set(e.split("@")[1] for e in emails))
    logger.info("DNS MX перевірка пошт Переможців для {} доменів...", len(domains))

    with ThreadPoolExecutor(max_workers=20) as executor:
        mx_results = list(executor.map(verify_mx, domains))
    domain_mx = dict(zip(domains, mx_results))

    df_sup["DNS MX"] = df_sup["✉️ Email Переможця"].map(
        lambda e: "✅ Active" if is_valid_email(str(e)) and domain_mx.get(str(e).split("@")[1], False) else ""
    )

    out_excel = OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.xlsx"
    out_csv = OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS_FULL_CONTACTS.csv"

    df_sup.to_csv(out_csv, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df_sup.to_excel(writer, index=False, sheet_name="Контакти Переможців")
        ws = writer.sheets["Контакти Переможців"]
        ws.freeze_panes = "A2"
        hfill = PatternFill(start_color="1A3C5E", end_color="1A3C5E", fill_type="solid")
        hfont = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        for col in range(1, len(df_sup.columns) + 1):
            c = ws.cell(row=1, column=col)
            c.fill = hfill
            c.font = hfont
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 30
        for idx, col_name in enumerate(df_sup.columns, 1):
            ws.column_dimensions[get_column_letter(idx)].width = 28

    logger.info("✅ ЗБЕРЕЖЕНО ПОВНІ КОНТАКТИ ПЕРЕМОЖЦІВ -> {}", out_excel)
    logger.info("Унікальних Переможців у реєстрі: {}", len(df_sup))
    logger.info("Переможців з прямим Email: {}", (df_sup["✉️ Email Переможця"] != "").sum())
    logger.info("Переможців з прямим телефоном: {}", (df_sup["📞 Телефон Переможця"] != "").sum())


if __name__ == "__main__":
    asyncio.run(main())
