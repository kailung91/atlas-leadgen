"""
Second-pass filter: fetch websites for "⚠️ перевірити" companies
and reclassify based on page title/description/headings.

Updates output/partner_leads_filtered.xlsx in place.
"""

from __future__ import annotations

import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")  # suppress SSL warnings

root = Path(__file__).resolve().parent.parent
XLSX = root / "output" / "partner_leads_filtered.xlsx"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 5
WORKERS = 15

# ── Same regex as filter_partners.py ─────────────────────────────────────────
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


def fetch_text(url: str) -> str | None:
    """Fetch title + meta description + h1/h2 from a URL. Returns None on error."""
    if not url or not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False, allow_redirects=True)
        if resp.status_code >= 400:
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
        parts = []
        if soup.title:
            parts.append(soup.title.get_text(" ", strip=True))
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            parts.append(meta["content"])
        for tag in soup.find_all(["h1", "h2"]):
            parts.append(tag.get_text(" ", strip=True))
        return " | ".join(parts)[:1000]
    except Exception:
        return None


def reclassify(text: str) -> tuple[str, str] | None:
    """Returns (new_status, reason) or None if unchanged."""
    if not text:
        return None
    has_include = INCLUDE.search(text)
    has_exclude = EXCLUDE.search(text)
    if has_include:
        return "✅ релевантний", f"Сайт: {has_include.group(0)}"
    if has_exclude:
        return "❌ відсіяти", f"Сайт: {has_exclude.group(0)[:30]}"
    return None


def main() -> None:
    print(f"Reading {XLSX}…")
    df_main = pd.read_excel(XLSX, sheet_name="Партнери", dtype=str).fillna("")
    df_excl = pd.read_excel(XLSX, sheet_name="Відсіяні", dtype=str).fillna("")

    candidates = df_main[
        (df_main["Фільтр"] == "⚠️ перевірити") & (df_main["Сайт"].str.strip() != "")
    ].copy()

    total = len(candidates)
    print(f"Candidates with website: {total}")

    results: dict[int, tuple[str, str]] = {}
    done = 0

    def process(idx: int, url: str) -> tuple[int, tuple[str, str] | None]:
        text = fetch_text(url)
        return idx, reclassify(text)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process, idx, row["Сайт"]): idx
                   for idx, row in candidates.iterrows()}
        for fut in as_completed(futures):
            idx, result = fut.result()
            if result:
                results[idx] = result
            done += 1
            if done % 100 == 0 or done == total:
                pct = done / total * 100
                out = f"\r  {done}/{total} ({pct:.0f}%)  ✅{sum(1 for s,_ in results.values() if s=='✅ релевантний')}  ❌{sum(1 for s,_ in results.values() if s=='❌ відсіяти')}"
                sys.stdout.write(out)
                sys.stdout.flush()

    print()

    # Apply results
    for idx, (status, reason) in results.items():
        df_main.at[idx, "Фільтр"] = status
        df_main.at[idx, "Причина"] = reason

    # Re-split sheets
    df_relevant = df_main[df_main["Фільтр"].isin(["✅ релевантний", "⚠️ перевірити"])].copy()
    df_excluded_new = df_main[df_main["Фільтр"] == "❌ відсіяти"].copy()
    df_excluded_all = pd.concat([df_excl, df_excluded_new], ignore_index=True)

    col_widths = {"A": 14, "B": 8, "C": 30, "D": 12, "E": 45, "F": 16,
                  "G": 45, "H": 22, "I": 28, "J": 28, "K": 50, "L": 30}

    with pd.ExcelWriter(XLSX, engine="openpyxl") as writer:
        for sheet_name, frame in [("Партнери", df_relevant), ("Відсіяні", df_excluded_all)]:
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for col, w in col_widths.items():
                ws.column_dimensions[col].width = w
            ws.freeze_panes = "A2"

    newly_relevant = sum(1 for s, _ in results.values() if s == "✅ релевантний")
    newly_excluded = sum(1 for s, _ in results.values() if s == "❌ відсіяти")
    remaining = (df_relevant["Фільтр"] == "⚠️ перевірити").sum()

    print("\nРезультат другого проходу:")
    print(f"  Нові ✅ релевантний : {newly_relevant}")
    print(f"  Нові ❌ відсіяти    : {newly_excluded}")
    print(f"  Залишилось ⚠️       : {remaining}")
    print(f"  Всього у Партнери   : {len(df_relevant)}")
    print(f"  Всього у Відсіяні   : {len(df_excluded_all)}")
    print(f"\nSaved → {XLSX}")


if __name__ == "__main__":
    main()
