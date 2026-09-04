"""
Filter partner_leads.xlsx — removes clearly irrelevant companies.

Logic:
  47.61, 47.62, 58.11, 46.18  → keep all (KVED already specific)
  46.49, 47.91                 → check products_services text:
      EXCLUDE keywords  → ❌ відсіяти
      INCLUDE keywords  → ✅ релевантний
      no description    → ⚠️ перевірити

Output:
  output/partner_leads_filtered.xlsx   (2 sheets: Партнери + Відсіяні)
  output/partner_leads_filtered.csv
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

root = Path(__file__).resolve().parent.parent

SRC = root / "output" / "partner_leads.xlsx"
DST_XLSX = root / "output" / "partner_leads_filtered.xlsx"
DST_CSV = root / "output" / "partner_leads_filtered.csv"

# ── Keyword lists ─────────────────────────────────────────────────────────────

# Clearly IRRELEVANT — exclude if products contain these
EXCLUDE = re.compile(
    r"електр|вимикач|кабель|дріт|провід|LED|ліхтар|освітлен|трансформ|генератор|лічильник"
    r"|сантехнік|труб|батарея|радіатор|клапан|фітинг"
    r"|вікн[аи]|двер[іи]|цемент|бетон|будівельн|плит[кі]|ламін|паркет|шпалер|штукатур|гіпсокартон"
    r"|меблі|матрац|диван|шафа|крісло|стелаж"
    r"|хліб|випічк|борошн|продукт|харчов|молоко|м.ясо|рибн|кавов|алкогол|напо[ї]"
    r"|одяг|взуття|текстиль|тканин|швейн|пряж"
    r"|авто|шини|мастил|моторн|автозапчаст|мото"
    r"|медичн|фармацевт|ліки|таблетк|хірург|стоматол"
    r"|метал|арматур|профіл|балк[аи]|листов|прокат"
    r"|упаковк|скотч|поліетилен|полімер|пластмас|стретч"
    r"|сільськ|агро|фермерств|добрив|насін|пестицид"
    r"|деревин|лісов|пиломатер|паркетн"
    r"|хімія|миючий|мийн|побутов.хімія|розчинник"
    r"|косметик|парфум|шампун|крем для"
    r"|нерухомість|оренда приміщень|ріелтор"
    r"|охорон|сигналізація|відеонагляд"
    r"|техніка для|обладнання для|устаткування для"
    r"|станки|верстат|зварювальн|токарн|фрезерн",
    re.IGNORECASE,
)

# Clearly RELEVANT — include if products contain these
INCLUDE = re.compile(
    r"книг|книжк|атлас|карт[аи]|карти|канцтовар|канцелярі"
    r"|папір|паперов|бланк|блокнот|щоденник|зошит|зошитів"
    r"|підручник|навчальн|освітн|шкільн|навчальна"
    r"|видавн|поліграф|друкарн|видання"
    r"|ручк[аи]|олівець|маркер|лінійк|ластик"
    r"|конверт|наклейк|стікер"
    r"|офісн|письмов|для офісу"
    r"|глобус|географ|топограф",
    re.IGNORECASE,
)

# KVEDs that are specific enough — don't filter by products
SAFE_KVEDS = {"47.61", "47.62", "58.11", "46.18"}
BROAD_KVEDS = {"46.49", "47.91"}


def classify(row: pd.Series) -> tuple[str, str]:
    """Returns (status, reason)."""
    kved = str(row.get("КVED", ""))
    products = str(row.get("Продукція/послуги", "") or "")

    if kved in SAFE_KVEDS:
        return "✅ релевантний", "КВЕД профільний"

    # broad KVED — check products
    if not products.strip() or products == "nan":
        return "⚠️ перевірити", "Немає опису продукції"

    if EXCLUDE.search(products):
        # double-check: if also has include keywords, keep
        if INCLUDE.search(products):
            return "✅ релевантний", "Профільна + інші товари"
        reason = EXCLUDE.search(products).group(0)[:30]
        return "❌ відсіяти", f"Нерелевантна продукція: {reason}…"

    if INCLUDE.search(products):
        return "✅ релевантний", "Профільна продукція"

    return "⚠️ перевірити", "Опис не дає однозначної відповіді"


def main() -> None:
    print(f"Reading {SRC}…")
    df = pd.read_excel(SRC, sheet_name="Партнери", dtype=str)
    df = df.fillna("")

    statuses, reasons = zip(*[classify(row) for _, row in df.iterrows()])
    df.insert(0, "Фільтр", statuses)
    df["Причина"] = reasons

    relevant = df[df["Фільтр"].isin(["✅ релевантний", "⚠️ перевірити"])].copy()
    excluded = df[df["Фільтр"] == "❌ відсіяти"].copy()

    print("\nРезультат:")
    print(f"  ✅ релевантний : {(df['Фільтр'] == '✅ релевантний').sum()}")
    print(f"  ⚠️ перевірити  : {(df['Фільтр'] == '⚠️ перевірити').sum()}")
    print(f"  ❌ відсіяти    : {(df['Фільтр'] == '❌ відсіяти').sum()}")

    print("\nПо КВЕДу (відсіяно):")
    if len(excluded):
        for kved, g in excluded.groupby("КVED"):
            print(f"  {kved}: {len(g)}")

    # Save CSV
    relevant.to_csv(DST_CSV, index=False, encoding="utf-8-sig")
    print(f"\nCSV → {DST_CSV}")

    # Save Excel with 2 sheets
    col_widths = {"A": 14, "B": 8, "C": 30, "D": 12, "E": 45, "F": 16,
                  "G": 45, "H": 22, "I": 28, "J": 28, "K": 50, "L": 30}

    with pd.ExcelWriter(DST_XLSX, engine="openpyxl") as writer:
        for sheet_name, frame in [("Партнери", relevant), ("Відсіяні", excluded)]:
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for col, w in col_widths.items():
                ws.column_dimensions[col].width = w
            ws.freeze_panes = "A2"

    print(f"Excel → {DST_XLSX}")
    print(f"\nГотово: {len(relevant)} партнерів залишено, {len(excluded)} відсіяно.")


if __name__ == "__main__":
    main()
