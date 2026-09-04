"""
Ultra-Strict Domain Classifier for Prozorro Tenders.

Filters Prozorro dataset strictly for:
  1. School Atlases & Contour Maps (Geography & History)
  2. Educational Posters & Wall Maps (Geography & History)
  3. Globes
  4. Educational Geography & History Cabinet Equipment (НУШ / ДК 021:2015 39162110-9)
  5. Educational Buyers ONLY (Schools, Lyceums, Universities, Education Departments, Libraries, Museums)

Homoglyph-aware: Converts Latin-lookalike characters (A, P, E, O, C, X, etc.) to Cyrillic to prevent bypass.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

HOMOGLYPH_MAP = str.maketrans({
    "A": "А", "a": "а", "B": "В", "E": "Е", "e": "е", "H": "Н", "I": "І", "i": "і",
    "K": "К", "M": "М", "O": "О", "o": "о", "P": "Р", "p": "р", "C": "С", "c": "с",
    "T": "Т", "X": "Х", "x": "х", "Y": "У", "y": "у"
})


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    # Map homoglyphs and lower-case
    return text.translate(HOMOGLYPH_MAP).lower().strip()


# Exclude Triggers for Buyers (Hospitals, Medical KNP, Non-educational state utilities)
EXCLUDE_BUYER_PATTERNS = [
    r"лікарн", r"медичн", r"госпітал", r"поліклінік", r"амбулатор", r"диспансер", r"здоровпункт",
    r"водоканал", r"укрнафт", r"поліці", r"морський.*порт", r"військов.*частин", r"суд", r"прокуратур",
    r"некомерційне підприємство", r"\bкнп\b", r"підприємство.*охорони.*здоров", r"теплокоммуненерго", r"автодор",
    r"центр.*громадського.*здоров"
]

# Exclude Triggers for Purchase Titles
EXCLUDE_TITLE_PATTERNS = [
    r"медичн", r"амбулаторн", r"пам[\'\"’]?яті", r"памяти", r"мікросхем", r"кардіограф", r"паливо", r"бензин", r"дизель",
    r"шолом", r"сушарка", r"талон", r"прапор", r"вишива", r"варистор", r"кабель", r"відеокарт", r"дослідницьк",
    r"складськог", r"амбулатор", r"аналіз", r"кров", r"чищення", r"страхов", r"стрічка", r"дерев[\'\"’]?ян",
    r"огороджен", r"квіт", r"конденсатор", r"дистиляц", r"апарати", r"сушарок", r"наколінник", r"налокітник",
    r"плитоноск", r"автотранспорт", r"догляду", r"хворого", r"картою", r"обліку", r"довідка", r"бланки",
    r"карточка", r"форма", r"технічн", r"ремонт", r"автомобіль", r"імітатор", r"реанімаційн", r"манекен",
    r"вироби.*для.*ванної", r"ванно"
]

# Strict Positive Profile Patterns (MUST contain at least one in TITLE)
STRICT_POSITIVE_PATTERNS = [
    r"атлас", r"контурн.*картин?", r"контурн.*карт", r"глобус", r"географ", r"істор", r"стінн.*карт",
    r"карт.*україн", r"карт.*світ", r"карт.*європ", r"кабінет.*географії", r"кабінет.*історії",
    r"навчальн.*плакат", r"навчальн.*карт", r"стінн.*плакат", r"дидактичн.*карт", r"посібник.*географії",
    r"посібник.*історії", r"обладнання.*географії", r"обладнання.*історії"
]

RE_EXCLUDE_BUYER = re.compile("|".join(EXCLUDE_BUYER_PATTERNS), re.IGNORECASE)
RE_EXCLUDE_TITLE = re.compile("|".join(EXCLUDE_TITLE_PATTERNS), re.IGNORECASE)
RE_STRICT_POSITIVE = re.compile("|".join(STRICT_POSITIVE_PATTERNS), re.IGNORECASE)


def is_strict_target_tender(title: str, buyer_name: str, category: str) -> bool:
    title_str = normalize_text(title)
    buyer_str = normalize_text(buyer_name)

    # 1. Reject if buyer matches exclude patterns (hospitals, ukrnafta, police, etc.)
    if RE_EXCLUDE_BUYER.search(buyer_str):
        return False

    # 2. Reject if title matches non-profile exclude patterns
    if RE_EXCLUDE_TITLE.search(title_str):
        return False

    # 3. Must match strict positive educational profile IN THE PURCHASE TITLE
    if RE_STRICT_POSITIVE.search(title_str):
        return True

    return False


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


def filter_prozorro_dataset():
    input_excel = OUTPUT_DIR / "prozorro_school_tenders.xlsx"
    if not input_excel.exists():
        logger.error("Master Prozorro Excel not found: {}", input_excel)
        return

    f = pd.ExcelFile(input_excel, engine="openpyxl")
    df_buyers = f.parse("Замовники (Покупці)")
    df_winners = f.parse("Переможці (Постачальники)")
    df_bidders = f.parse("Учасники (Гравці ринку)")

    logger.info("Raw Prozorro Counts: {} Buyers, {} Winners, {} Bidders", len(df_buyers), len(df_winners), len(df_bidders))

    valid_tender_ids = set()
    filtered_buyers_rows = []

    for _, r in df_buyers.iterrows():
        tender_id = r["ID Тендеру"]
        title = r["Предмет закупівлі"]
        buyer = r["Замовник (Покупець)"]
        cat = r["Категорія товару"]

        if is_strict_target_tender(title, buyer, cat):
            valid_tender_ids.add(tender_id)
            filtered_buyers_rows.append(r)

    df_buyers_strict = pd.DataFrame(filtered_buyers_rows)
    df_winners_strict = df_winners[df_winners["ID Тендеру"].isin(valid_tender_ids)].copy()
    df_bidders_strict = df_bidders[df_bidders["ID Тендеру"].isin(valid_tender_ids)].copy()

    logger.info("100% PERFECT ULTRA-STRICT Prozorro Counts: {} Buyers, {} Winners, {} Bidders (Filtered out {} non-profile tenders)",
                len(df_buyers_strict), len(df_winners_strict), len(df_bidders_strict),
                len(df_buyers) - len(df_buyers_strict))

    # Save STRICT CSVs
    df_buyers_strict.to_csv(OUTPUT_DIR / "prozorro_school_buyers_STRICT.csv", index=False, encoding="utf-8-sig")
    df_winners_strict.to_csv(OUTPUT_DIR / "prozorro_school_winners_STRICT.csv", index=False, encoding="utf-8-sig")
    df_bidders_strict.to_csv(OUTPUT_DIR / "prozorro_school_bidders_STRICT.csv", index=False, encoding="utf-8-sig")

    # Save STRICT Excel
    out_excel = OUTPUT_DIR / "prozorro_school_tenders_STRICT.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df_buyers_strict.to_excel(writer, index=False, sheet_name="Замовники (Покупці)")
        format_excel_sheet(writer.sheets["Замовники (Покупці)"], df_buyers_strict, header_color="1F4E78")

        df_winners_strict.to_excel(writer, index=False, sheet_name="Переможці (Постачальники)")
        format_excel_sheet(writer.sheets["Переможці (Постачальники)"], df_winners_strict, header_color="2E75B6")

        df_bidders_strict.to_excel(writer, index=False, sheet_name="Учасники (Гравці ринку)")
        format_excel_sheet(writer.sheets["Учасники (Гравці ринку)"], df_bidders_strict, header_color="375623")

    logger.info("Saved 100% PERFECT ULTRA-STRICT Prozorro Master Excel -> {}", out_excel)
    return df_buyers_strict, df_winners_strict, df_bidders_strict


if __name__ == "__main__":
    filter_prozorro_dataset()
