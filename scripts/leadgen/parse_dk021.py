"""
Парсер ДК 021:2015 — пошук всіх розділів, пов'язаних з:
картами, атласами, глобусами, географією, освітою, навчальними матеріалами
"""
import re
from docx import Document

doc = Document("f451914n23.doc")

# Збираємо весь текст таблиць (класифікатор у таблицях)
KEYWORDS = [
    "карт", "атлас", "глобус", "географ", "картограф",
    "навчальн", "освіт", "шкільн", "підручник", "посібник",
    "плакат", "стінн", "навчаль", "контурн", "зошит",
    "видання", "друков", "книг",
]

results = []

# Пошук у параграфах
for para in doc.paragraphs:
    text = para.text.strip()
    if not text:
        continue
    tl = text.lower()
    if any(k in tl for k in KEYWORDS):
        results.append(("PARA", text))

# Пошук у таблицях
for table in doc.tables:
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        row_text = " | ".join(cells)
        tl = row_text.lower()
        if any(k in tl for k in KEYWORDS):
            results.append(("TABLE", row_text))

print(f"Знайдено {len(results)} рядків\n")
print("=" * 100)

seen = set()
for typ, text in results:
    if text in seen:
        continue
    seen.add(text)
    # Витягуємо CPV код якщо є
    codes = re.findall(r"\d{8}-\d", text)
    code_str = f"[{', '.join(codes)}] " if codes else ""
    print(f"{code_str}{text}")
