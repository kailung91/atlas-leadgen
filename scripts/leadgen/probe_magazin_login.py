"""
Test logins for 1C Magazin database
"""
import win32com.client

path = r'G:\Мій диск\Work\База 1С\1C8_Data_Base\Магазин'
passwords_to_try = ["", "12345", "admin", "Admin", "Cjpthwfybt!33"]
users_to_try = ["admin", "Админ", "api", "Администратор"]

connector = win32com.client.Dispatch("V83.COMConnector")

for u in users_to_try:
    for p in passwords_to_try:
        conn_str = f'File="{path}";Usr="{u}";Pwd="{p}";'
        try:
            v83 = connector.Connect(conn_str)
            print(f"SUCCESS! User: '{u}', Password: '{p}'")
            meta = v83.Метаданные.Справочники.Контрагенты
            print("Magazin Контрагенты attributes:")
            for i in range(meta.Реквизиты.Количество()):
                attr = meta.Реквизиты.Получить(i)
                print(f"  - {attr.Имя}")
            del v83
            break
        except Exception as e:
            pass
