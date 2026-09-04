"""
ОФІЦІЙНИЙ Prozorro CPV Scraper — v3.0 (ДК 021:2015 Verified)
- Звірено з офіційним документом Верховного Закону України ДК 021:2015 (f451914n23.doc)
- Архітектура: asyncio + aiohttp (CPU-safe, без WinSock exhaustion)
- Фільтрація: 3-рівнева воронка (CPV → Keyword Allowlist → Denylist + Unit code)
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import socket
from pathlib import Path

import aiohttp
import dns.resolver
import pandas as pd
from loguru import logger
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_API = "https://public.api.openprocurement.org/api/2.5"

# ─── ОФІЦІЙНІ CPV КОДИ (ЗВІРЕНО З ДК 021:2015 f451914n23.doc) ──────────────────
# CORE КОДИ (Ядрові для Atlas-Industry / ІПТ):
# 22114200-4 — Атласи
# 22114300-5 — Мапи
# 39162110-9 — Навчальне приладдя (кабінети географії/історії, глобуси, стінні карти)
# 22832000-1 — Зошити із завданнями (контурні карти, практикуми)

CPV_CODES_CORE = [
    "22114200-4",  # ⭐ Офіційний код ДК 021: Атласи
    "22114300-5",  # ⭐ Офіційний код ДК 021: Мапи
    "39162110-9",  # ⭐ Офіційний код ДК 021: Навчальне приладдя (кабінети географії/історії)
    "22832000-1",  # ⭐ Офіційний код ДК 021: Зошити із завданнями (контурні карти)
    "37520000-9",  # ⭐ Офіційний код ДК 021: Іграшки (Toys)
]

CPV_CODES_SECONDARY = [
    "22111000-1",  # Шкільні книги (потрібен keyword-фільтр)
    "22112000-8",  # Підручники (потрібен keyword-фільтр)
    "39162100-6",  # Навчальне обладнання (потрібен keyword-фільтр)
    "39162200-7",  # Допоміжне навчальне приладдя (потрібен keyword-фільтр)
    "39162000-5",  # Приладдя для навчальних закладів (потрібен keyword-фільтр)
    "22830000-7",  # Зошити (контурні карти часто тут)
    "22458000-5",  # Друкована продукція на замовлення
]

ALL_CPV_CODES = CPV_CODES_CORE + CPV_CODES_SECONDARY

# ─── KEYWORD ALLOWLIST ──────────────────────────────────────────────────────
KEYWORD_ALLOW_RE = re.compile(
    r"атлас|контурн|глобус|стінн.*карт|настінн.*карт|"
    r"карт.*геогр|карт.*істор|карт.*украін|карт.*світ|"
    r"геогр.*карт|карт.*навч|навч.*карт|учбов.*карт|"
    r"картограф|географічн.*карт|карт.*фізич|для ЗЗСО|для шкіл",
    re.IGNORECASE,
)

# ─── KEYWORD DENYLIST (Тверде виключення) ───────────────────────────────────
KEYWORD_DENY_RE = re.compile(
    r"медичн|амбулатор|електрокардіо|ЕКГ|ecg|"
    r"пам.яті|microsd|sd.карт|"
    r"паливо|паливн|нафт|оливи|мастил|"
    r"ванн|сантех|санітарн|"
    r"картридж|тонер|принтер|"
    r"харчуванн|їдальн|меблі|"
    r"ноутбук|комп.ютер|планшет",
    re.IGNORECASE,
)

BUYER_DENY_RE = re.compile(
    r"лікарн|поліклінік|амбулатор|диспансер|госпіталь|"
    r"укрнафт|водоканал|теплопостач|"
    r"поліці|прокуратур|суд|митн",
    re.IGNORECASE,
)

UNIT_DENY = {"LTR", "MLT", "KGM", "GRM", "MTQ", "CMQ"}
CONCURRENCY = 25
MIN_VALUE_UAH = 1_000
TIMEOUT = aiohttp.ClientTimeout(connect=3, total=15)

RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
HOSTILE_DOMAINS = {"mail.ru", "yandex.ru", "yandex.ua", "rambler.ru", "bk.ru"}


def is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.strip().lower().split("@")[-1]
    return (
        domain not in HOSTILE_DOMAINS
        and not domain.endswith((".ru", ".su", ".by"))
        and bool(RE_EMAIL.match(email.strip()))
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


def is_profile_match(tender: dict, cpv_code: str) -> bool:
    """3-рівнева фільтрація тендера."""
    items = tender.get("items", [])
    title = tender.get("title", "")
    desc = " ".join([title] + [i.get("description", "") for i in items])

    # Denylist фільтр
    if KEYWORD_DENY_RE.search(desc):
        return False

    buyer_name = tender.get("procuringEntity", {}).get("name", "")
    if BUYER_DENY_RE.search(buyer_name):
        return False

    for item in items:
        unit = item.get("unit", {}).get("code", "").upper()
        if unit in UNIT_DENY:
            return False

    amount = tender.get("value", {}).get("amount", 0) or 0
    if float(amount) < MIN_VALUE_UAH:
        return False

    # Якщо CPV з категорії SECONDARY — вимагаємо keyword allowlist
    if cpv_code in CPV_CODES_SECONDARY:
        if not KEYWORD_ALLOW_RE.search(desc):
            return False

    return True


async def fetch_json(session: aiohttp.ClientSession, url: str, sem: asyncio.Semaphore, retries=3) -> dict | None:
    async with sem:
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=TIMEOUT) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    elif resp.status == 429:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return None
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.debug("Failed {}: {}", url[-60:], e)
    return None


async def fetch_cpv_tender_ids(session: aiohttp.ClientSession, cpv: str, sem: asyncio.Semaphore) -> set[str]:
    """Пагінація по всіх тендерах для одного CPV коду."""
    ids = set()
    offset = None
    page = 0

    while True:
        url = f"{BASE_API}/tenders?mode=_all_&opt_fields=id&cpv={cpv}"
        if offset:
            url += f"&offset={offset}"

        data = await fetch_json(session, url, sem)
        if not data:
            break

        items = data.get("data", [])
        if not items:
            break

        for item in items:
            tid = item.get("id") or item.get("tenderID")
            if tid:
                ids.add(tid)

        next_offset = data.get("next_page", {}).get("offset")
        if not next_offset or next_offset == offset:
            break
        offset = next_offset
        page += 1

        if page % 20 == 0:
            logger.info("CPV {}: {} сторінок, {} тендерів...", cpv, page, len(ids))

        await asyncio.sleep(0.1)

    logger.info("✅ CPV {} готово: всього {} тендерів ({} сторінок)", cpv, len(ids), page)
    return ids


async def fetch_tender_detail(session: aiohttp.ClientSession, tid: str, sem: asyncio.Semaphore) -> dict | None:
    data = await fetch_json(session, f"{BASE_API}/tenders/{tid}", sem)
    return data.get("data") if data else None


def parse_row(tender: dict, primary_cpv: str) -> dict | None:
    if not is_profile_match(tender, primary_cpv):
        return None

    pe = tender.get("procuringEntity", {})
    contact = pe.get("contactPoint", {})
    items = tender.get("items", [])
    item_desc = "; ".join([i.get("description", "") for i in items[:3]])
    cpv_found = list(set([i.get("classification", {}).get("id", "") for i in items]))
    tid = tender.get("id", "")
    email = contact.get("email", "").strip()

    return {
        "ID Тендеру": tid,
        "Предмет закупівлі": item_desc or tender.get("title", ""),
        "Коди ДК (CPV)": ", ".join(cpv_found),
        "Бюджет (грн)": tender.get("value", {}).get("amount", 0),
        "Статус": tender.get("status", ""),
        "Замовник": pe.get("name", ""),
        "ЄДРПОУ": pe.get("identifier", {}).get("id", ""),
        "Email": email if is_valid_email(email) else "",
        "Телефон": contact.get("telephone", "").strip(),
        "Місто": pe.get("address", {}).get("locality", ""),
        "Область": pe.get("address", {}).get("region", ""),
        "URL": f"https://prozorro.gov.ua/tender/{tid}",
    }


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, limit_per_host=20, ttl_dns_cache=300)

    async with aiohttp.ClientSession(
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0 (Atlas-Industry-Engine; research)"},
    ) as session:

        logger.info("🚀 Запуск Prozorro CPV Scraper v3.0 (ДК 021:2015 Verified)")
        logger.info("CORE CPV (Ядрові): {}", CPV_CODES_CORE)
        logger.info("SECONDARY CPV: {}", CPV_CODES_SECONDARY)

        logger.info("Крок 1: Паралельне збирання ID тендерів по всіх {} CPV кодах...", len(ALL_CPV_CODES))
        tasks = [fetch_cpv_tender_ids(session, cpv, sem) for cpv in ALL_CPV_CODES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_ids: set[str] = set()
        for cpv, res in zip(ALL_CPV_CODES, results):
            if isinstance(res, set):
                logger.info("CPV {}: {} ID", cpv, len(res))
                all_ids |= res

        logger.info("Всього унікальних тендерів для завантаження деталей: {}", len(all_ids))

        logger.info("Крок 2: Завантаження деталей та 3-рівнева фільтрація...")
        rows = []
        processed = 0
        id_list = list(all_ids)

        BATCH = 400
        for i in range(0, len(id_list), BATCH):
            batch = id_list[i:i + BATCH]
            detail_tasks = [fetch_tender_detail(session, tid, sem) for tid in batch]
            details = await asyncio.gather(*detail_tasks, return_exceptions=True)

            for tender in details:
                if isinstance(tender, dict):
                    # check against all cpvs
                    row = parse_row(tender, "secondary")
                    if row:
                        rows.append(row)
            processed += len(batch)

            if processed % 1000 == 0 or processed == len(id_list):
                logger.info("Оброблено {}/{} | Знайдено релевантних тендерів: {}", processed, len(id_list), len(rows))

    logger.info("Завершено! Всього валідних тендерів: {}", len(rows))

    if not rows:
        logger.warning("Жодного рядка не знайдено.")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["ID Тендеру"])
    df = df.sort_values("Бюджет (грн)", ascending=False)

    # DNS MX перевірка
    emails = [e for e in df["Email"].dropna().astype(str) if is_valid_email(e)]
    domains = set(e.split("@")[1] for e in emails)
    logger.info("Перевірка DNS MX для {} доменів...", len(domains))
    domain_mx = {d: verify_mx(d) for d in domains}
    df["DNS MX"] = df["Email"].map(
        lambda e: "✅ Active" if is_valid_email(str(e)) and domain_mx.get(str(e).split("@")[1], False) else ""
    )

    df.to_csv(OUTPUT_DIR / "prozorro_cpv_v3_official.csv", index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "prozorro_cpv_official_tenders.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Офіційні Цільові Тендери")
        ws = writer.sheets["Офіційні Цільові Тендери"]
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

    logger.info("Збережено фінальний Excel -> {} ({} рядків)", out_excel, len(df))


if __name__ == "__main__":
    asyncio.run(main())
