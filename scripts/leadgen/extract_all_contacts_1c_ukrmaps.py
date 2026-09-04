"""
Senior-Level Contact Extraction Pipeline for 1C DWH & Ukrmaps.com E-commerce.

Sources:
  1. 1C DWH (G:/Мій диск/Work/База 1С/1c_exports/clients_unique.csv & group_sales_2023_2025.csv) -> 2,330 B2B Counterparties
  2. Ukrmaps.com (D:/Codex/ukrmaps/backup/customers/old_customers.csv) -> 487 Registered E-commerce Customers
"""

from __future__ import annotations

import os
from pathlib import Path
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

G_DRIVE_EXPORTS = Path("G:/Мій диск/Work/База 1С/1c_exports")
UKRMAPS_DIR = Path("D:/Codex/ukrmaps")


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


def process_1c_contacts() -> pd.DataFrame:
    clients_csv = G_DRIVE_EXPORTS / "clients_unique.csv"
    if not clients_csv.exists():
        logger.warning("1C clients CSV not found: {}", clients_csv)
        return pd.DataFrame()

    df = pd.read_csv(clients_csv)
    logger.info("Loaded 1C Counterparties: {} records", len(df))

    # Rename & reorder columns cleanly
    df.rename(columns={
        "Контрагент": "Контрагент (1С)",
        "Сума": "Загальний сумарний виторг (грн)",
        "Кількість": "Кількість угод / операцій",
        "Код": "Код 1С",
        "Група": "Група Контрагента",
        "Бази": "Джерельна база 1С",
    }, inplace=True)

    df.sort_values(by="Загальний сумарний виторг (грн)", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)

    out_csv = OUTPUT_DIR / "1c_counterparties_contacts.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    
    out_excel = OUTPUT_DIR / "1c_counterparties_contacts.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Контрагенти 1С")
        format_excel_sheet(writer.sheets["Контрагенти 1С"], df, header_color="1F4E78")

    logger.info("Saved 1C Counterparties export -> {}", out_excel)
    return df


def process_ukrmaps_customers() -> pd.DataFrame:
    cust_csv = UKRMAPS_DIR / "backup" / "customers" / "old_customers.csv"
    if not cust_csv.exists():
        logger.warning("Ukrmaps customers CSV not found: {}", cust_csv)
        return pd.DataFrame()

    df = pd.read_csv(cust_csv, sep=";")
    logger.info("Loaded Ukrmaps Customers: {} records", len(df))

    df["full_name"] = (df["firstname"].fillna("") + " " + df["lastname"].fillna("")).str.strip()

    df_clean = pd.DataFrame({
        "ID Покупця": df["customer_id"],
        "ПІБ / Назва Покупця": df["full_name"],
        "Email": df["email"],
        "Телефон": df["telephone"],
        "Статус розсилки": df["newsletter"].map({1: "Підписаний", 0: "Ні"}),
        "Виконаних замовлень": df["orders_completed"],
        "Сума всіх замовлень (грн)": df["orders_total"],
        "Дата останнього замовлення": df["last_order_date"],
        "Дата реєстрації": df["date_added"],
    })

    df_clean.sort_values(by="Сума всіх замовлень (грн)", ascending=False, inplace=True)
    df_clean.reset_index(drop=True, inplace=True)

    out_csv = OUTPUT_DIR / "ukrmaps_ecommerce_customers.csv"
    df_clean.to_csv(out_csv, index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "ukrmaps_ecommerce_customers.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        df_clean.to_excel(writer, index=False, sheet_name="Покупці ukrmaps.com")
        format_excel_sheet(writer.sheets["Покупці ukrmaps.com"], df_clean, header_color="2E75B6")

    logger.info("Saved Ukrmaps Customers export -> {}", out_excel)
    return df_clean


def main():
    logger.info("Starting Contact Extraction Pipeline for 1C DWH & Ukrmaps.com...")
    df_1c = process_1c_contacts()
    df_ukr = process_ukrmaps_customers()

    master_excel = OUTPUT_DIR / "ecosystem_1c_ukrmaps_contacts.xlsx"
    with pd.ExcelWriter(master_excel, engine="openpyxl") as writer:
        if not df_1c.empty:
            df_1c.to_excel(writer, index=False, sheet_name="Контрагенти 1С")
            format_excel_sheet(writer.sheets["Контрагенти 1С"], df_1c, header_color="1F4E78")
        if not df_ukr.empty:
            df_ukr.to_excel(writer, index=False, sheet_name="Клієнти ukrmaps.com")
            format_excel_sheet(writer.sheets["Клієнти ukrmaps.com"], df_ukr, header_color="2E75B6")

    logger.info("Successfully generated Ecosystem Master Excel -> {}", master_excel)


if __name__ == "__main__":
    main()
