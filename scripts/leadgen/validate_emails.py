"""
Email validation: regex + MX lookup.
Оновлює partner_leads_filtered.xlsx — прибирає невалідні email.
Вихід: output/emails_invalid.csv — список відсіяних.

Usage: py -X utf8 scripts/validate_emails.py [--no-mx]
"""
from __future__ import annotations

import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import dns.resolver
import pandas as pd

ROOT    = Path(__file__).resolve().parent.parent
EXCEL   = ROOT / "output" / "partner_leads_filtered.xlsx"
INVALID = ROOT / "output" / "emails_invalid.csv"

# RFC 5322 спрощений
EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Явно невалідні / сміттєві шаблони
JUNK_RE = re.compile(
    r"(noreply|no-reply|donotreply|admin@admin|test@test|example\.|@localhost|\.invalid$)",
    re.IGNORECASE,
)

MX_CACHE: dict[str, bool] = {}
NO_MX = "--no-mx" in sys.argv


def valid_syntax(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and not JUNK_RE.search(email)


def has_mx(domain: str) -> bool:
    if domain in MX_CACHE:
        return MX_CACHE[domain]
    try:
        dns.resolver.resolve(domain, "MX", lifetime=5)
        MX_CACHE[domain] = True
    except Exception:
        MX_CACHE[domain] = False
    return MX_CACHE[domain]


def validate(email: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not email:
        return False, "empty"
    if not valid_syntax(email):
        return False, "bad_syntax"
    if NO_MX:
        return True, "ok"
    domain = email.split("@")[1]
    if not has_mx(domain):
        return False, "no_mx"
    return True, "ok"


def main() -> None:
    print(f"Читаємо {EXCEL}…")
    df = pd.read_excel(EXCEL, sheet_name="Партнери", dtype=str).fillna("")

    mask_rel = df["Фільтр"] == "✅ релевантний"
    mask_email = df["Email"].str.strip() != ""
    candidates = df[mask_rel & mask_email].copy()

    total = len(candidates)
    print(f"Релевантних з email: {total}")
    print("Валідуємо…" + (" (тільки синтаксис, --no-mx)" if NO_MX else " (синтаксис + MX)"))

    results: dict[int, tuple[bool, str]] = {}
    done = 0

    def check(idx: int, email: str) -> tuple[int, bool, str]:
        ok, reason = validate(email)
        return idx, ok, reason

    workers = 1 if NO_MX else 30
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(check, idx, row["Email"]): idx
                for idx, row in candidates.iterrows()}
        for fut in as_completed(futs):
            idx, ok, reason = fut.result()
            results[idx] = (ok, reason)
            done += 1
            if done % 50 == 0 or done == total:
                bad = sum(1 for v, _ in results.values() if not v)
                print(f"  {done}/{total}  ❌ {bad}", end="\r")

    print()

    invalid_rows = []
    for idx, (ok, reason) in results.items():
        if not ok:
            row = df.loc[idx]
            df.at[idx, "Email"] = ""          # очищаємо email
            df.at[idx, "Причина"] = reason
            invalid_rows.append({
                "Назва":  row["Назва"],
                "Email":  row["Email"],
                "Причина": reason,
            })

    # Зберігаємо invalid CSV
    with INVALID.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Назва", "Email", "Причина"])
        w.writeheader()
        w.writerows(invalid_rows)

    # Записуємо назад в Excel
    col_widths = {"A": 14, "B": 8, "C": 30, "D": 12, "E": 45,
                  "F": 16, "G": 45, "H": 22, "I": 28, "J": 28, "K": 50, "L": 30}
    df_excl = pd.read_excel(EXCEL, sheet_name="Відсіяні", dtype=str).fillna("")
    with pd.ExcelWriter(EXCEL, engine="openpyxl") as writer:
        for name, frame in [("Партнери", df), ("Відсіяні", df_excl)]:
            frame.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            for col, w in col_widths.items():
                ws.column_dimensions[col].width = w
            ws.freeze_panes = "A2"

    valid   = sum(1 for v, _ in results.values() if v)
    invalid = len(invalid_rows)
    print(f"\n✅ Валідних   : {valid}")
    print(f"❌ Невалідних : {invalid}")
    print(f"   → {INVALID}")
    print("   Excel оновлено: невалідні email очищено")


if __name__ == "__main__":
    main()
