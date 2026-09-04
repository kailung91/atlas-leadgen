"""
Senior-Level Prozorro Multi-Entity Lead Processor (A+ Grade).

Tracks:
  1. Procuring Entities / Buyers (Замовники: Школи, Відділи освіти, ЗВО)
  2. Tender Winners / Contractors (Переможці / Постачальники / Дистриб'ютори)
  3. Bidders / Participants (Учасники тендерів / Конкуренти)

Export Excel Sheets:
  - Sheet 1: "Замовники (Покупці)"
  - Sheet 2: "Переможці (Постачальники)"
  - Sheet 3: "Учасники (Гравці ринку)"
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
RAW_DIR = ROOT / "data" / "raw" / "prozorro_tenders"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISCARD_DOMAINS = {"example.com", "domain.com", "test.com", "email.com"}
HOSTILE_SUFFIXES = (".ru", ".su", ".by", ".xn--p1ai")
HOSTILE_DOMAINS = {
    "mail.ru", "yandex.ru", "yandex.ua", "yandex.com", "rambler.ru",
    "bk.ru", "inbox.ru", "list.ru", "mail.ua", "ok.ru", "vk.com",
    "lenta.ru", "bk.ru", "ya.ru"
}


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


def classify_product_category(title: str, desc: str = "") -> str:
    combined = f"{title} {desc}".lower()
    categories = []
    if any(k in combined for k in ["атлас", "атласи"]):
        categories.append("Шкільні Атласи")
    if any(k in combined for k in ["карта", "карти", "картограф"]):
        categories.append("Географічні / Історичні Карти")
    if any(k in combined for k in ["глобус", "глобуси"]):
        categories.append("Глобуси")
    if any(k in combined for k in ["кабінет географії", "кабінет історії", "дидактич"]):
        categories.append("Обладнання Кабінетів Географії та Історії")

    return " | ".join(categories) if categories else "Навчальне Обладнання & Карти"


def format_excel_sheet(ws, df: pd.DataFrame, header_color: str = "1F4E78") -> None:
    ws.freeze_panes = "A2"

    header_fill = PatternFill(start_color=header_color, end_color=header_color, fill_type="solid")
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


def process_prozorro_entities() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    jsonl_file = RAW_DIR / "prozorro_school_tenders.jsonl"
    if not jsonl_file.exists():
        logger.warning("Prozorro jsonl file does not exist: {}", jsonl_file)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    buyers: list[dict] = []
    winners: list[dict] = []
    bidders: list[dict] = []

    seen_buyers: set[str] = set()
    seen_winners: set[str] = set()
    seen_bidders: set[str] = set()

    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue

            tid = t.get("tenderID") or t.get("id")
            if not tid:
                continue

            title = t.get("title") or ""
            desc = t.get("description") or ""
            category = classify_product_category(title, desc)
            amount = (t.get("value") or {}).get("amount") or 0.0
            status = t.get("status") or "active"

            # 1. Process Buyer (Procuring Entity)
            entity = t.get("procuringEntity", {})
            contact = entity.get("contactPoint", {})
            address_obj = entity.get("address", {})
            raw_email = (contact.get("email") or "").lower().strip()
            b_email = raw_email if validate_email(raw_email) else ""
            b_phone = (contact.get("telephone") or "").strip()
            b_contact = (contact.get("name") or "").strip()
            buyer_name = entity.get("name") or entity.get("identifier", {}).get("legalName") or ""
            b_edrpou = entity.get("identifier", {}).get("id") or ""
            b_city = address_obj.get("locality") or ""
            b_region = address_obj.get("region") or ""

            buyer_key = f"{tid}_{b_edrpou}"
            if buyer_key not in seen_buyers:
                seen_buyers.add(buyer_key)
                buyers.append({
                    "ID Тендеру": tid,
                    "Категорія товару": category,
                    "Предмет закупівлі": title,
                    "Бюджет (грн)": amount,
                    "Статус закупівлі": status,
                    "Замовник (Покупець)": buyer_name,
                    "ЄДРПОУ Замовника": b_edrpou,
                    "Контактна особа": b_contact,
                    "Email Замовника": b_email,
                    "Телефон Замовника": b_phone,
                    "Місто": b_city,
                    "Область": b_region,
                    "URL Тендеру": f"https://prozorro.gov.ua/tender/{tid}",
                })

            # 2. Process Winners (Awards & Contracts)
            awards = t.get("awards", [])
            for award in awards:
                a_status = award.get("status")
                suppliers = award.get("suppliers", [])
                a_amount = (award.get("value") or {}).get("amount") or amount

                for supp in suppliers:
                    w_name = supp.get("name") or supp.get("identifier", {}).get("legalName") or ""
                    w_edrpou = supp.get("identifier", {}).get("id") or ""
                    w_contact = supp.get("contactPoint", {})
                    raw_w_email = (w_contact.get("email") or "").lower().strip()
                    w_email = raw_w_email if validate_email(raw_w_email) else ""
                    w_phone = (w_contact.get("telephone") or "").strip()
                    w_contact_person = (w_contact.get("name") or "").strip()
                    w_addr = supp.get("address", {})
                    w_city = w_addr.get("locality") or ""

                    w_key = f"{tid}_{w_edrpou}_{w_name}"
                    if w_key not in seen_winners:
                        seen_winners.add(w_key)
                        winners.append({
                            "ID Тендеру": tid,
                            "Статус рішення": a_status,
                            "Переможець / Постачальник": w_name,
                            "Код ЄДРПОУ / ІПН": w_edrpou,
                            "Сума виграшу (грн)": a_amount,
                            "Контактна особа": w_contact_person,
                            "Email Переможця": w_email,
                            "Телефон Переможця": w_phone,
                            "Місто переможця": w_city,
                            "Предмет закупівлі": title,
                            "Замовник": buyer_name,
                            "URL Тендеру": f"https://prozorro.gov.ua/tender/{tid}",
                        })

            # 3. Process Bidders (Participants)
            bids = t.get("bids", [])
            for bid in bids:
                bid_status = bid.get("status")
                bid_amount = (bid.get("value") or {}).get("amount") or 0.0
                tenderers = bid.get("tenderers", [])

                for tend in tenderers:
                    part_name = tend.get("name") or tend.get("identifier", {}).get("legalName") or ""
                    part_edrpou = tend.get("identifier", {}).get("id") or ""
                    part_contact = tend.get("contactPoint", {})
                    raw_part_email = (part_contact.get("email") or "").lower().strip()
                    part_email = raw_part_email if validate_email(raw_part_email) else ""
                    part_phone = (part_contact.get("telephone") or "").strip()
                    part_contact_person = (part_contact.get("name") or "").strip()
                    part_city = (tend.get("address") or {}).get("locality") or ""

                    bid_key = f"{tid}_{part_edrpou}_{part_name}"
                    if bid_key not in seen_bidders:
                        seen_bidders.add(bid_key)
                        bidders.append({
                            "ID Тендеру": tid,
                            "Статус пропозиції": bid_status,
                            "Учасник (Конкурент/Партнер)": part_name,
                            "Код ЄДРПОУ / ІПН": part_edrpou,
                            "Запропонована ціна (грн)": bid_amount,
                            "Контактна особа": part_contact_person,
                            "Email Учасника": part_email,
                            "Телефон Учасника": part_phone,
                            "Місто учасника": part_city,
                            "Предмет закупівлі": title,
                            "Замовник": buyer_name,
                            "URL Тендеру": f"https://prozorro.gov.ua/tender/{tid}",
                        })

    df_buyers = pd.DataFrame(buyers)
    df_winners = pd.DataFrame(winners)
    df_bidders = pd.DataFrame(bidders)

    logger.info("Processed Prozorro Entities: {} Buyers, {} Winners, {} Bidders", len(df_buyers), len(df_winners), len(df_bidders))

    # Export CSVs
    if not df_buyers.empty:
        df_buyers.to_csv(OUTPUT_DIR / "prozorro_school_buyers.csv", index=False, encoding="utf-8-sig")
    if not df_winners.empty:
        df_winners.to_csv(OUTPUT_DIR / "prozorro_school_winners.csv", index=False, encoding="utf-8-sig")
    if not df_bidders.empty:
        df_bidders.to_csv(OUTPUT_DIR / "prozorro_school_bidders.csv", index=False, encoding="utf-8-sig")

    # Export Multi-Sheet Master Excel
    excel_out = OUTPUT_DIR / "prozorro_school_tenders.xlsx"
    with pd.ExcelWriter(excel_out, engine="openpyxl") as writer:
        if not df_buyers.empty:
            df_buyers.to_excel(writer, index=False, sheet_name="Замовники (Покупці)")
            format_excel_sheet(writer.sheets["Замовники (Покупці)"], df_buyers, header_color="1F4E78")

        if not df_winners.empty:
            df_winners.to_excel(writer, index=False, sheet_name="Переможці (Постачальники)")
            format_excel_sheet(writer.sheets["Переможці (Постачальники)"], df_winners, header_color="2E75B6")

        if not df_bidders.empty:
            df_bidders.to_excel(writer, index=False, sheet_name="Учасники (Гравці ринку)")
            format_excel_sheet(writer.sheets["Учасники (Гравці ринку)"], df_bidders, header_color="548235")

    logger.info("Saved A+ Senior Prozorro Multi-Entity Excel -> {}", excel_out)
    return df_buyers, df_winners, df_bidders


if __name__ == "__main__":
    process_prozorro_entities()
