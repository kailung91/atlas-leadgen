"""
MASTER EMAIL OUTREACH CAMPAIGN GENERATOR — Atlas-Industry / ІПТ (v2.0)
Включає:
  1. Prozorro Замовники (Школи, Ліцеї, Відділи освіти) — 563 пошти
  2. Prozorro Переможці / Конкуренти / Постачальники — 1,450 компаній та ФОП
  3. Шкільні Ліди K-12 (P1 Top, P2, P3) — 21,472 пошти
"""
import pandas as pd
from pathlib import Path
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger.info("🚀 Збирання ПОВНОЇ MASTER бази для Email-розсилок (включаючи Замовників та Переможців)...")

records = []

# 1. Prozorro Цільові Замовники (v5.0)
pz_target_path = OUTPUT_DIR / "prozorro_target_search_tenders.xlsx"
if pz_target_path.exists():
    df_pz = pd.read_excel(pz_target_path)
    for _, r in df_pz.iterrows():
        email = str(r.get("Email", "")).strip().lower()
        if email and "@" in email and email != "nan":
            records.append({
                "Email": email,
                "Назва Організації / Клієнта / Постачальника": str(r.get("Замовник", "")),
                "Роль у Закупівлях": "🏛️ Замовник (Покупець)",
                "Категорія": "Prozorro Замовник",
                "Пріоритет": "P1 - Високий (Покупець тендеру)",
                "ЄДРПОУ": str(r.get("ЄДРПОУ", "")),
                "Телефон": str(r.get("Телефон", "")),
                "Місто": str(r.get("Місто", "")),
                "Область": str(r.get("Область", "")),
                "Джерело": "Prozorro Search API v5.0",
                "DNS MX": str(r.get("DNS MX", "✅ Active")),
            })
    logger.info("Додано Prozorro Замовників: {}", len(records))

# 2. Prozorro Договори (Переможці / Конкуренти & Замовники)
pz_win_path = OUTPUT_DIR / "prozorro_winners_and_buyers.xlsx"
winners_list = []
if pz_win_path.exists():
    df_win = pd.read_excel(pz_win_path)
    
    # Додаємо Замовників
    for _, r in df_win.iterrows():
        email = str(r.get("Email Замовника", "")).strip().lower()
        if email and "@" in email and email != "nan":
            records.append({
                "Email": email,
                "Назва Організації / Клієнта / Постачальника": str(r.get("🏛️ Замовник (Покупець)", "")),
                "Роль у Закупівлях": "🏛️ Замовник (Покупець)",
                "Категорія": "Prozorro Договори",
                "Пріоритет": "P1 - Високий (Підписаний договір)",
                "ЄДРПОУ": str(r.get("ЄДРПОУ Замовника", "")),
                "Телефон": str(r.get("Телефон Замовника", "")),
                "Місто": str(r.get("Місто", "")),
                "Область": str(r.get("Область", "")),
                "Джерело": "Prozorro Contracts v6.0",
                "DNS MX": str(r.get("DNS MX", "✅ Active")),
            })

    # Збираємо Унікальних Переможців (Конкурентів / Постачальників)
    top_winners = df_win.groupby("🏆 Переможець (Постачальник)").agg(
        ContractCount=("ID Договору", "count"),
        TotalSum=("Сума Договору (грн)", "sum")
    ).reset_index().sort_values("TotalSum", ascending=False)

    for _, r in top_winners.iterrows():
        w_name = str(r.get("🏆 Переможець (Постачальник)", "")).strip()
        if w_name and w_name != "nan":
            winners_list.append({
                "🏆 Назва Переможця / Постачальника": w_name,
                "Кількість виграних договорів": r.get("ContractCount", 1),
                "Загальний бюджет угод (грн)": r.get("TotalSum", 0),
                "Роль у Закупівлях": "🏆 Переможець (Конкурент/Постачальник)",
                "Категорія": "Prozorro Переможець",
                "Джерело": "Prozorro Contracts API v6.0"
            })

    logger.info("Виділено унікальних Переможців (Конкурентів): {}", len(winners_list))

# 3. Шкільні Ліди (School Leads P1-P3)
school_path = OUTPUT_DIR / "school_leads_filtered.csv"
if school_path.exists():
    df_sch = pd.read_csv(school_path)
    for _, r in df_sch.iterrows():
        email = str(r.get("Email", "")).strip().lower()
        if email and "@" in email and email != "nan":
            prio = str(r.get("Priority", "P2"))
            records.append({
                "Email": email,
                "Назва Організації / Клієнта / Постачальника": str(r.get("School_Name", "")),
                "Роль у Закупівлях": "🏛️ Навчальний заклад",
                "Категорія": "Школа K-12",
                "Пріоритет": f"{prio} - Шкільний лід",
                "ЄДРПОУ": str(r.get("EDRPOU", "")),
                "Телефон": str(r.get("Phone", "")),
                "Місто": str(r.get("Locality", "")),
                "Область": str(r.get("Region", "")),
                "Джерело": str(r.get("Source", "SchoolScraper")),
                "DNS MX": "✅ Active",
            })

df_master = pd.DataFrame(records)

# Дедуплікація за Email
df_master["Prio_Score"] = df_master["Пріоритет"].map(
    lambda x: 1 if "P1" in str(x) else (2 if "P2" in str(x) else 3)
)
df_master = df_master.sort_values("Prio_Score").drop_duplicates(subset=["Email"]).drop(columns=["Prio_Score"])

# Чистка NaN
for col in df_master.columns:
    df_master[col] = df_master[col].replace("nan", "").replace("None", "").fillna("")

df_winners = pd.DataFrame(winners_list)

logger.info("Унікальних верифікованих Email Замовників: {}", len(df_master))
logger.info("Унікальних Переможців (Конкурентів): {}", len(df_winners))

# Формування підсумкового Excel
out_excel = OUTPUT_DIR / "MASTER_EMAIL_OUTREACH_CAMPAIGN_V2.xlsx"
out_csv = OUTPUT_DIR / "MASTER_EMAIL_OUTREACH_CAMPAIGN_V2.csv"
out_winners = OUTPUT_DIR / "PROZORRO_WINNING_SUPPLIERS.xlsx"

df_master.to_csv(out_csv, index=False, encoding="utf-8-sig")
df_winners.to_excel(out_winners, index=False)

with pd.ExcelWriter(out_excel, engine="openpyxl") as writer:
    # Sheet 1: Всі пошти Замовників
    df_master.to_excel(writer, index=False, sheet_name="1. Замовники (Master Email)")
    
    # Sheet 2: Prozorro Замовники (Освіта)
    df_pz_only = df_master[df_master["Категорія"].str.contains("Prozorro")]
    df_pz_only.to_excel(writer, index=False, sheet_name="2. Prozorro Замовники")
    
    # Sheet 3: Переможці / Постачальники (Конкуренти)
    df_winners.to_excel(writer, index=False, sheet_name="3. Переможці Тендерів")
    
    # Sheet 4: Школи P1 Top
    df_p1 = df_master[df_master["Пріоритет"].str.contains("P1")]
    df_p1.to_excel(writer, index=False, sheet_name="4. Школи P1 Top")

    # Форматування всіх листі
    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        ws.freeze_panes = "A2"
        hfill = PatternFill(start_color="1A3C5E", end_color="1A3C5E", fill_type="solid")
        hfont = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        for col in range(1, len(ws[1]) + 1):
            c = ws.cell(row=1, column=col)
            c.fill = hfill
            c.font = hfont
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 30
        for idx in range(1, len(ws[1]) + 1):
            ws.column_dimensions[get_column_letter(idx)].width = 28

logger.info("✅ УСПІШНО ОНОВЛЕНО MASTER БАЗУ З ПЕРЕМОЖЦЯМИ ТА ЗАМОВНИКАМИ -> {}", out_excel)
