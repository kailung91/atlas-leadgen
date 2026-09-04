"""
Senior-Level 1C Split Processor for UTP (IPT) and Magazin (Магазин) Databases.

Generates 2 distinct standalone Excel & CSV packages:
  1. 1C UTP (IPT) Base Database -> 1c_base_utp_ipt_contacts.xlsx / .csv
  2. 1C Magazin Base Database -> 1c_base_magazin_contacts.xlsx / .csv
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


def generate_utp_ipt_database():
    clients_csv = G_DRIVE_EXPORTS / "clients_unique.csv"
    sales_csv = G_DRIVE_EXPORTS / "group_sales_2023_2025.csv"

    # 1. Clients belonging to IPT / UTP
    df_clients = pd.read_csv(clients_csv)
    utp_clients = df_clients[df_clients["Бази"].fillna("").str.contains("IPT", case=False)].copy()
    utp_clients.sort_values(by="Сума", ascending=False, inplace=True)
    utp_clients.reset_index(drop=True, inplace=True)

    # 2. Sales transactions for UTP / IPT
    df_sales = pd.read_csv(sales_csv)
    utp_sales = df_sales[df_sales["База"] == "IPT"].copy()

    # Aggregate top purchased items per counterparty for UTP
    counterparty_summary = utp_sales.groupby("Контрагент").agg(
        Сума_Продажу_2023_2025=("Сума", "sum"),
        Кількість_Одиниць=("Кількість", "sum"),
        Кількість_Операцій=("Номенклатура", "count"),
        Головна_Група_Товарів=("ГрупаТовару", lambda s: s.mode().iloc[0] if not s.empty and not s.mode().empty else "")
    ).reset_index()

    # Merge client metadata with sales summary
    merged_utp = utp_clients.merge(counterparty_summary, left_on="Контрагент", right_on="Контрагент", how="left")
    merged_utp["Сума_Продажу_2023_2025"] = merged_utp["Сума_Продажу_2023_2025"].fillna(merged_utp["Сума"])

    merged_utp.rename(columns={
        "Контрагент": "Контрагент (1С UTP)",
        "Сума": "Загальний виторг 1С (грн)",
        "Кількість": "Кількість операцій",
        "Код": "Код 1С",
        "Група": "Група Контрагента",
        "Бази": "Всі виявлені бази",
        "Сума_Продажу_2023_2025": "Виторг 2023-2025 (грн)",
        "Кількість_Одиниць": "Обсяг закуплених товарів (шт)",
        "Головна_Група_Товарів": "Основна номенклатурна група",
    }, inplace=True)

    out_csv = OUTPUT_DIR / "1c_base_utp_ipt_contacts.csv"
    merged_utp.to_csv(out_csv, index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "1c_base_utp_ipt_contacts.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        merged_utp.to_excel(writer, index=False, sheet_name="База UTP (ІПТ)")
        format_excel_sheet(writer.sheets["База UTP (ІПТ)"], merged_utp, header_color="1F4E78")

        # Sheet 2: Top Sales items in UTP
        top_items_utp = utp_sales.groupby(["Номенклатура", "ГрупаТовару"]).agg(
            Загальний_Виторг=("Сума", "sum"),
            Продано_Штук=("Кількість", "sum"),
            Кількість_Угод=("Контрагент", "count")
        ).reset_index().sort_values(by="Загальний_Виторг", ascending=False)

        top_items_utp.to_excel(writer, index=False, sheet_name="ТОП Товари UTP")
        format_excel_sheet(writer.sheets["ТОП Товари UTP"], top_items_utp, header_color="1F4E78")

    logger.info("Generated 1C UTP (IPT) Database: {} counterparties -> {}", len(merged_utp), out_excel)
    return merged_utp


def generate_magazin_database():
    clients_csv = G_DRIVE_EXPORTS / "clients_unique.csv"
    sales_csv = G_DRIVE_EXPORTS / "group_sales_2023_2025.csv"

    # 1. Clients belonging to Magazin
    df_clients = pd.read_csv(clients_csv)
    mag_clients = df_clients[df_clients["Бази"].fillna("").str.contains("Magazin", case=False)].copy()
    mag_clients.sort_values(by="Сума", ascending=False, inplace=True)
    mag_clients.reset_index(drop=True, inplace=True)

    # 2. Sales transactions for Magazin
    df_sales = pd.read_csv(sales_csv)
    mag_sales = df_sales[df_sales["База"] == "Magazin"].copy()

    # Aggregate top purchased items per counterparty for Magazin
    counterparty_summary = mag_sales.groupby("Контрагент").agg(
        Сума_Продажу_2023_2025=("Сума", "sum"),
        Кількість_Одиниць=("Кількість", "sum"),
        Кількість_Операцій=("Номенклатура", "count"),
        Головна_Група_Товарів=("ГрупаТовару", lambda s: s.mode().iloc[0] if not s.empty and not s.mode().empty else "")
    ).reset_index()

    # Merge client metadata with sales summary
    merged_mag = mag_clients.merge(counterparty_summary, left_on="Контрагент", right_on="Контрагент", how="left")
    merged_mag["Сума_Продажу_2023_2025"] = merged_mag["Сума_Продажу_2023_2025"].fillna(merged_mag["Сума"])

    merged_mag.rename(columns={
        "Контрагент": "Контрагент (1С Магазин)",
        "Сума": "Загальний виторг 1С (грн)",
        "Кількість": "Кількість операцій",
        "Код": "Код 1С",
        "Група": "Група Контрагента",
        "Бази": "Всі виявлені бази",
        "Сума_Продажу_2023_2025": "Виторг 2023-2025 (грн)",
        "Кількість_Одиниць": "Обсяг закуплених товарів (шт)",
        "Головна_Група_Товарів": "Основна номенклатурна група",
    }, inplace=True)

    out_csv = OUTPUT_DIR / "1c_base_magazin_contacts.csv"
    merged_mag.to_csv(out_csv, index=False, encoding="utf-8-sig")

    out_excel = OUTPUT_DIR / "1c_base_magazin_contacts.xlsx"
    with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
        merged_mag.to_excel(writer, index=False, sheet_name="База Магазин")
        format_excel_sheet(writer.sheets["База Магазин"], merged_mag, header_color="2E75B6")

        # Sheet 2: Top Sales items in Magazin
        top_items_mag = mag_sales.groupby(["Номенклатура", "ГрупаТовару"]).agg(
            Загальний_Виторг=("Сума", "sum"),
            Продано_Штук=("Кількість", "sum"),
            Кількість_Угод=("Контрагент", "count")
        ).reset_index().sort_values(by="Загальний_Виторг", ascending=False)

        top_items_mag.to_excel(writer, index=False, sheet_name="ТОП Товари Магазин")
        format_excel_sheet(writer.sheets["ТОП Товари Магазин"], top_items_mag, header_color="2E75B6")

    logger.info("Generated 1C Magazin Database: {} counterparties -> {}", len(merged_mag), out_excel)
    return merged_mag


def main():
    logger.info("Executing 1C Split Database Processor for UTP (IPT) and Magazin...")
    generate_utp_ipt_database()
    generate_magazin_database()
    logger.info("1C Separate Database Extraction Completed Successfully!")


if __name__ == "__main__":
    main()
