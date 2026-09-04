"""
Senior-Level Higher Education (ЗВО / ВНЗ) Leads Data Processor & Ranker.

Target Category:
  - Higher Education Institutions (Universities, Academies, Institutes, Colleges)
  - Focus Offer: Geography & History Wall Maps & Educational Posters (Карти, Навчальні Плакати з Географії та Історії)

Features:
  - Target Profile Classification (Педагогічний / Географічний / Історичний / Класичний / Технічний)
  - Strict .ru / hostile domain filtering
  - Multi-key deduplication (Email + Name / EDRPOU + Name / Name + City)
  - Priority Ranking (P1 -> P4)
  - Dual-sheet OpenPyXL Excel generation with frozen panes & column auto-fit
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISCARD_DOMAINS = {"example.com", "domain.com", "test.com", "email.com"}
HOSTILE_SUFFIXES = (".ru", ".su", ".by", ".xn--p1ai")
HOSTILE_DOMAINS = {
    "mail.ru", "yandex.ru", "yandex.ua", "yandex.com", "rambler.ru",
    "bk.ru", "inbox.ru", "list.ru", "mail.ua", "ok.ru", "vk.com",
    "lenta.ru", "bk.ru", "ya.ru"
}

HIGH_PRIORITY_KEYWORDS = [
    "педагогіч", "педуніверситет", "гуманітарн", "національний університет",
    "географ", "істор", "картограф", "краєзнав", "еколог"
]


def validate_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    email = email.strip().lower()
    if len(email) < 6 or len(email) > 100:
        return False
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        return False
    domain = email.split("@")[-1]
    if domain in DISCARD_DOMAINS or domain in HOSTILE_DOMAINS:
        return False
    if any(domain.endswith(suffix) for suffix in HOSTILE_SUFFIXES):
        return False
    return True


def normalize_hei_name(name: str) -> str:
    if not name:
        return ""
    name = re.sub(r'["«»\'”’]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip().lower()


def classify_hei_profile(name: str, desc: str = "") -> str:
    combined = f"{name} {desc}".lower()
    if any(k in combined for k in ["педагогіч", "педуніверситет"]):
        return "Педагогічний ЗВО (Підготовка вчителів історії/географії)"
    if any(k in combined for k in ["географ", "картограф", "геодез"]):
        return "Географічний / Природничий ЗВО"
    if any(k in combined for k in ["істор", "археолог", "гуманітарн"]):
        return "Історичний / Гуманітарний ЗВО"
    if "національний" in combined and "університет" in combined:
        return "Класичний Національний Університет"
    if "коледж" in combined or "технікум" in combined:
        return "Фаховий Коледж / Технікум"
    if "академія" in combined or "інститут" in combined:
        return "Академія / Науково-навчальний Інститут"
    return "Загальний ЗВО / ВНЗ"


def compute_hei_priority(row: dict) -> int:
    has_email = bool(row.get("Email"))
    has_phone = bool(row.get("Телефони"))
    has_director = bool(row.get("Директор / Ректор"))
    profile = row.get("Цільовий напрямок", "")

    is_high_target = any(k in profile.lower() for k in ["педагогіч", "географіч", "історич", "класичний"])

    if has_email and has_phone and is_high_target:
        return 1
    if has_email and has_phone:
        return 2
    if has_email:
        return 3
    return 4


def format_excel_sheet(ws, df: pd.DataFrame) -> None:
    ws.freeze_panes = "A2"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")

    for col in range(1, len(df.columns) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, col_name in enumerate(df.columns, 1):
        sample_vals = df[col_name].dropna().astype(str).head(100)
        max_len = max([len(str(v)) for v in sample_vals] + [len(col_name)])
        col_letter = get_column_letter(idx)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 55)


def process_hei_leads() -> tuple[pd.DataFrame, pd.DataFrame]:
    records: list[dict] = []
    seen_keys: set[str] = set()

    # 1. Process portal HEI jsonl files (osvita.ua/vnz)
    portal_dir = RAW_DIR / "hei_portals"
    if portal_dir.exists():
        for pfile in portal_dir.glob("*.jsonl"):
            logger.info("Processing HEI portal file: {}", pfile.name)
            with open(pfile, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue

                    raw_email = (r.get("email") or "").lower().strip()
                    email = raw_email if validate_email(raw_email) else ""
                    name = r.get("name") or ""
                    city = r.get("city") or ""
                    edrpou = r.get("edrpou") or ""

                    if email:
                        dedup_key = f"{email}_{normalize_hei_name(name)}"
                    elif edrpou:
                        dedup_key = f"{edrpou}_{normalize_hei_name(name)}"
                    else:
                        dedup_key = f"{normalize_hei_name(name)}_{city.lower()}"

                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    profile = classify_hei_profile(name, r.get("target_profile", ""))

                    rec = {
                        "Джерело": r.get("source", "osvita.ua/vnz"),
                        "КВЕД": "85.42",
                        "Сфера": "Вища освіта (Університети, Академії, Інститути)",
                        "ЄДРПОУ": edrpou,
                        "Назва ЗВО": name,
                        "Коротка назва": r.get("short_name", ""),
                        "Цільовий напрямок": profile,
                        "Пропозиція": "Навчальні плакати (Географія, Історія) & Карти",
                        "Директор / Ректор": r.get("director", ""),
                        "Місто": city,
                        "Адреса": r.get("address", ""),
                        "Телефони": r.get("phone", ""),
                        "Email": email,
                        "Сайт": r.get("website", ""),
                        "URL джерела": r.get("url", ""),
                    }
                    rec["Пріоритет"] = compute_hei_priority(rec)
                    records.append(rec)

    # 2. Process UA Region HEI jsonl files (KVEDs 85.42, 85.41, 85.32)
    ua_hei_dir = RAW_DIR / "ua_region_hei"
    if ua_hei_dir.exists():
        for ufile in sorted(ua_hei_dir.glob("*.jsonl")):
            logger.info("Processing HEI KVED file: {}", ufile.name)
            with open(ufile, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue

                    raw_email = (r.get("email") or "").lower().strip()
                    email = raw_email if validate_email(raw_email) else ""
                    name = r.get("name") or ""
                    city = r.get("city") or ""
                    edrpou = r.get("edrpou") or ""

                    if email:
                        dedup_key = f"{email}_{normalize_hei_name(name)}"
                    elif edrpou:
                        dedup_key = f"{edrpou}_{normalize_hei_name(name)}"
                    else:
                        dedup_key = f"{normalize_hei_name(name)}_{city.lower()}"

                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    profile = classify_hei_profile(name, r.get("kved_desc", ""))

                    rec = {
                        "Джерело": "ua-region.com.ua",
                        "КВЕД": r.get("kved", "85.42"),
                        "Сфера": r.get("kved_desc", "Вища та фахова передвища освіта"),
                        "ЄДРПОУ": edrpou,
                        "Назва ЗВО": name,
                        "Коротка назва": r.get("short_name", ""),
                        "Цільовий напрямок": profile,
                        "Пропозиція": "Навчальні плакати (Географія, Історія) & Карти",
                        "Директор / Ректор": r.get("director", ""),
                        "Місто": city,
                        "Адреса": r.get("address", ""),
                        "Телефони": r.get("phone", ""),
                        "Email": email,
                        "Сайт": r.get("website", ""),
                        "URL джерела": r.get("url", ""),
                    }
                    rec["Пріоритет"] = compute_hei_priority(rec)
                    records.append(rec)

    df_all = pd.DataFrame(records)
    if df_all.empty:
        logger.warning("No HEI records processed!")
        return pd.DataFrame(), pd.DataFrame()

    df_p1_p3 = df_all[df_all["Пріоритет"].isin([1, 2, 3])].copy()
    df_p4 = df_all[df_all["Пріоритет"] == 4].copy()

    df_p1_p3.sort_values(by=["Пріоритет", "Назва ЗВО"], inplace=True)
    df_p1_p3.reset_index(drop=True, inplace=True)

    df_p4.sort_values(by=["Назва ЗВО"], inplace=True)
    df_p4.reset_index(drop=True, inplace=True)

    # Export CSV
    csv_out = OUTPUT_DIR / "hei_leads_filtered.csv"
    df_p1_p3.to_csv(csv_out, index=False, encoding="utf-8-sig")
    logger.info("Saved HEI Primary CSV -> {}", csv_out)

    # Export Senior Excel
    excel_out = OUTPUT_DIR / "hei_leads_filtered.xlsx"
    with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
        df_p1_p3.to_excel(writer, index=False, sheet_name="ЗВО України (P1-P3)")
        format_excel_sheet(writer.sheets["ЗВО України (P1-P3)"], df_p1_p3)

        if not df_p4.empty:
            df_p4.to_excel(writer, index=False, sheet_name="ЗВО без Email (P4)")
            format_excel_sheet(writer.sheets["ЗВО без Email (P4)"], df_p4)

    logger.info("Saved A+ Senior Dual-Sheet HEI Excel -> {}", excel_out)
    return df_p1_p3, df_p4


if __name__ == "__main__":
    process_hei_leads()
