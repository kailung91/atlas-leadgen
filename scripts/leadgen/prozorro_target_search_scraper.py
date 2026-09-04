"""
ОФІЦІЙНИЙ Повнотекстовий Скрапер Prozorro Search API — v5.0 (Kimi K3 Audited & Fixed)
- Знайдено та виправлено Kimi K3:
  1. Prozorro Search API повертає ВСІ деталі замовника та предмету прямо у відповіді — не потрібно робити 500 окремих запитів до Public API!
  2. Твердо захищено від None/Null-помилок JSON (Safe Get dict chaining)
  3. Оптимізовано Denylist: прибрано занадто жорстоке "меблі" (оскільки кабінети географії часто закуповують меблі+карти)
  4. Асинхронна DNS MX верифікація через aio-resolver / ThreadPoolExecutor
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

SEARCH_API = "https://prozorro.gov.ua/api/search/tenders"

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
    "карта настінна",
    "карта України настінна",
    "обладнання кабінету географії",
    "обладнання кабінету історії",
    "навчальні плакати географія",
    "дидактичні матеріали географія",
]

# Ключові слова виключення (прибрали надмірне 'меблі')
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
    r"поліці|прокуратур|суд|митн",
    re.IGNORECASE,
)

UNIT_DENY = {"LTR", "MLT", "KGM", "GRM", "MTQ", "CMQ"}
MIN_VALUE_UAH = 1_000
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


def is_profile_match(tender: dict) -> bool:
    """Null-safe 3-рівнева фільтрація тендера."""
    title = tender.get("title") or ""
    items = tender.get("items") or []
    item_descs = [i.get("description") or "" for i in items if isinstance(i, dict)]
    desc = " ".join([title] + item_descs)

    # 1. Denylist перевірка
    if KEYWORD_DENY_RE.search(desc):
        return False

    pe = tender.get("procuringEntity") or {}
    buyer_name = pe.get("name") or ""
    if BUYER_DENY_RE.search(buyer_name):
        return False

    # 2. Одиниця виміру (паливо/рідини)
    for item in items:
        if isinstance(item, dict):
            unit = (item.get("unit") or {}).get("code") or ""
            if unit.upper() in UNIT_DENY:
                return False

    # 3. Сума тендеру
    val = tender.get("value") or {}
    amount = val.get("amount") or 0
    try:
        if float(amount) < MIN_VALUE_UAH:
            return False
    except (ValueError, TypeError):
        pass

    return True


async def search_query(session: aiohttp.ClientSession, query: str, sem: asyncio.Semaphore) -> list[dict]:
    """Пагінація по офіційному пошуковому API Prozorro з підтримкою повторів (retries)."""
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    tenders = []
    page = 1
    per_page = 100

    async with sem:
        while True:
            payload = {"text": query, "page": page, "per_page": per_page}
            success = False

            for attempt in range(3):
                try:
                    async with session.post(SEARCH_API, json=payload, headers=headers, timeout=TIMEOUT) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            items = data.get("data") or []
                            total = data.get("total") or 0

                            if not items:
                                success = True
                                break

                            tenders.extend(items)

                            # Зупиняємо якщо завантажили все або досягли глибини 50 сторінок (5,000 тендерів)
                            if len(tenders) >= total or page >= 50:
                                success = True
                                break

                            page += 1
                            success = True
                            await asyncio.sleep(0.1)
                            break

                        elif resp.status == 429:
                            await asyncio.sleep(2 ** (attempt + 1))
                        else:
                            break
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))

            if not success or page > 50 or (total > 0 and len(tenders) >= total):
                break

    logger.info("✅ Запит '{}': знайдено {} тендерів", query, len(tenders))
    return tenders


def parse_tender_row(tender: dict) -> dict | None:
    """Null-safe парсинг тендерного рядка з пошукового результату."""
    if not is_profile_match(tender):
        return None

    pe = tender.get("procuringEntity") or {}
    contact = pe.get("contactPoint") or {}
    ident = pe.get("identifier") or {}
    addr = pe.get("address") or {}
    val = tender.get("value") or {}
    items = tender.get("items") or []

    item_descs = [i.get("description") or "" for i in items if isinstance(i, dict)]
    item_desc = "; ".join([d for d in item_descs[:3] if d])
    cpv_found = list(set([(i.get("classification") or {}).get("id") or "" for i in items if isinstance(i, dict)]))
    cpv_found = [c for c in cpv_found if c]

    tid = tender.get("tenderID") or tender.get("id") or ""
    email = (contact.get("email") or "").strip()

    return {
        "ID Тендеру": tid,
        "Предмет закупівлі": item_desc or tender.get("title") or "",
        "Коди ДК (CPV)": ", ".join(cpv_found),
        "Бюджет (грн)": val.get("amount") or 0,
        "Статус": tender.get("status") or "",
        "Замовник": pe.get("name") or ident.get("legalName") or "",
        "ЄДРПОУ": ident.get("id") or "",
        "Email": email if is_valid_email(email) else "",
        "Телефон": (contact.get("telephone") or "").strip(),
        "Місто": addr.get("locality") or "",
        "Область": addr.get("region") or "",
        "URL": f"https://prozorro.gov.ua/tender/{tid}" if tid else "",
    }


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)

    async with aiohttp.ClientSession(connector=connector) as session:
        logger.info("🚀 Запуск Prozorro Search Scraper v5.0 (Kimi K3 Audited)")
        logger.info("Пошукових фраз: {}", len(TARGET_QUERIES))

        # Крок 1: Пошук по всіх фразах
        tasks = [search_query(session, q, sem) for q in TARGET_QUERIES]
        search_results = await asyncio.gather(*tasks, return_exceptions=True)

        raw_tenders_dict = {}
        for query, res in zip(TARGET_QUERIES, search_results):
            if isinstance(res, list):
                for item in res:
                    tid = item.get("tenderID") or item.get("id")
                    if tid and tid not in raw_tenders_dict:
                        raw_tenders_dict[tid] = item

        logger.info("Всього унікальних тендерів із пошуку: {}", len(raw_tenders_dict))

        # Крок 2: Опрацювання цільових тендерів
        rows = []
        for tender in raw_tenders_dict.values():
            row = parse_tender_row(tender)
            if row:
                rows.append(row)

        logger.info("100% Цільових навчальних тендерів після 3-рівневого фільтру: {}", len(rows))

    if not rows:
        logger.warning("Нуль цільових тендерів у базі.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["ID Тендеру"])
    df = df.sort_values("Бюджет (грн)", ascending=False)

    # Паралельна DNS MX перевірка в ThreadPool
    emails = [e for e in df["Email"].dropna().astype(str) if is_valid_email(e)]
    domains = list(set(e.split("@")[1] for e in emails))
    logger.info("Паралельна DNS MX перевірка для {} доменів...", len(domains))

    with ThreadPoolExecutor(max_workers=20) as executor:
        mx_results = list(executor.map(verify_mx, domains))
    domain_mx = dict(zip(domains, mx_results))

    df["DNS MX"] = df["Email"].map(
        lambda e: "✅ Active" if is_valid_email(str(e)) and domain_mx.get(str(e).split("@")[1], False) else ""
    )

    # Збереження результатів
    df.to_csv(OUTPUT_DIR / "prozorro_target_search_tenders.csv", index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "prozorro_target_search_tenders.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Цільові Навчальні Тендери")
        ws = writer.sheets["Цільові Навчальні Тендери"]
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

    logger.info("✅ Збережено Excel -> {} ({} рядків)", out_excel.name, len(df))
    logger.info("Замовників з активною поштою (DNS MX Active): {}", df["DNS MX"].eq("✅ Active").sum())


if __name__ == "__main__":
    asyncio.run(main())
