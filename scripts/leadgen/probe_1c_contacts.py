"""
Extract 1C Contact Register Data (Phones, Emails, Addresses, EDRPOU) via COMConnector.
"""

from __future__ import annotations

import os
from pathlib import Path
import win32com.client
import pandas as pd
from loguru import logger

BASE_DIR = r"G:\Мій диск\Work\База 1С\1C8_Data_Base"
OUT_DIR = Path("D:/Codex/redactor/atlas-industry-engine/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = [
    {"name": "UTP_IPT", "path": BASE_DIR + r"\UTP", "user": "Админ", "pwd": "Cjpthwfybt!33"},
    {"name": "Magazin", "path": BASE_DIR + r"\Магазин", "user": "admin", "pwd": ""},
    {"name": "Magazin_api", "path": BASE_DIR + r"\Магазин", "user": "api", "pwd": "12345"},
]

QUERY_CONTACTS = """
ВЫБРАТЬ
    Контрагенты.Код КАК Код,
    Контрагенты.Наименование КАК Назва,
    Контрагенты.НаименованиеПолное КАК ПовнаНазва,
    Контрагенты.КодПоОКПО КАК ЄДРПОУ,
    Контрагенты.ИНН КАК ІПН,
    КонтактнаяИнформация.Тип КАК Тип,
    КонтактнаяИнформация.Вид.Наименование КАК Вид,
    КонтактнаяИнформация.Представление КАК Представлення
ИЗ
    Справочник.Контрагенты КАК Контрагенты
    ЛЕВОЕ СОЕДИНЕНИЕ РегистрСведений.КонтактнаяИнформация КАК КонтактнаяИнформация
    ПО КонтактнаяИнформация.Объект = Контрагенты.Ссылка
"""


def unwrap(v):
    if v is None:
        return ""
    if isinstance(v, (int, float, bool, str)):
        return str(v)
    return str(v)


def extract_db_contacts(db_info):
    conn_str = f'File="{db_info["path"]}";Usr="{db_info["user"]}";Pwd="{db_info["pwd"]}";'
    logger.info("Connecting to 1C [{}] at {}...", db_info['name'], db_info['path'])
    
    try:
        connector = win32com.client.Dispatch("V83.COMConnector")
        v83 = connector.Connect(conn_str)
        logger.info("  Successfully connected to 1C [{}]!", db_info['name'])

        q = v83.NewObject("Запрос")
        q.Текст = QUERY_CONTACTS
        executed = q.Выполнить()
        cols = [c.Name for c in executed.Колонки]
        sel = executed.Выбрать()

        rows = []
        while sel.Следующий():
            row = {c: unwrap(getattr(sel, c)) for c in cols}
            row["База"] = db_info["name"]
            rows.append(row)

        del v83, connector
        df = pd.DataFrame(rows)
        logger.info("  Extracted {} contact records from [{}]!", len(df), db_info['name'])
        return df
    except Exception as e:
        logger.error("  Failed to connect/query [{}]: {}", db_info['name'], e)
        return pd.DataFrame()


def main():
    for db in DATABASES:
        df = extract_db_contacts(db)
        if not df.empty:
            out_file = OUT_DIR / f"1c_raw_contacts_{db['name']}.csv"
            df.to_csv(out_file, index=False, encoding="utf-8-sig")
            logger.info("Saved 1C raw contacts -> {}", out_file)


if __name__ == "__main__":
    main()
