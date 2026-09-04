"""
Probe 1C Metadata attributes for Справочник.Контрагенты and РегистрСведений.КонтактнаяИнформация
"""

import win32com.client

conn_str = r'File="G:\Мій диск\Work\База 1С\1C8_Data_Base\UTP";Usr="Админ";Pwd="Cjpthwfybt!33";'

try:
    connector = win32com.client.Dispatch("V83.COMConnector")
    v83 = connector.Connect(conn_str)
    print("Connected to UTP!")

    # Check Metadata attributes of Контрагенты
    meta = v83.Метаданные.Справочники.Контрагенты
    print("\nAttributes of Справочник.Контрагенты:")
    for i in range(meta.Реквизиты.Количество()):
        attr = meta.Реквизиты.Получить(i)
        print(f"  - {attr.Имя} ({attr.Синоним})")

    # Check Metadata attributes of КонтактнаяИнформация register
    meta_ci = v83.Метаданные.РегистрыСведений.КонтактнаяИнформация
    print("\nAttributes of РегистрСведений.КонтактнаяИнформация:")
    for i in range(meta_ci.Реквизиты.Количество()):
        attr = meta_ci.Реквизиты.Получить(i)
        print(f"  - {attr.Имя} ({attr.Синоним})")
    print("\nDimensions (Измерения):")
    for i in range(meta_ci.Измерения.Количество()):
        dim = meta_ci.Измерения.Получить(i)
        print(f"  - {dim.Имя} ({dim.Синоним})")
    print("\nResources (Ресурсы):")
    for i in range(meta_ci.Ресурсы.Количество()):
        res = meta_ci.Ресурсы.Получить(i)
        print(f"  - {res.Имя} ({res.Синоним})")

    del v83, connector
except Exception as e:
    print(f"Error: {e}")
