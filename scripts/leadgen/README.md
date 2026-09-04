# scripts/leadgen/ — Lead Generation Engine для ІПТ

Окремий бізнес-напрям (з 2026-07-28): генерація лідів для email-кампанії видавця шкільних атласів — школи, ЗВО, книгарні/дистриб'ютори, переможці/замовники тендерів Prozorro, збагачення 1C-баз контактами. **Не залежить від картографічного пайплайну** в `scripts/` (карти машинобудування/хімії) — спільний лише корінь репо. Готові датасети: `output/MASTER_EMAIL_OUTREACH_CAMPAIGN_FINAL.xlsx` та інші, перелік у корневому `README.md`.

Переміщено сюди з `scripts/` 2026-08-19 (файли не змінені, лише розташування) — див. `scripts/README.md` для картографічного ядра.

## 🏛️ Prozorro (тендери/договори/переможці)

| Скрипт | Призначення |
|---|---|
| `prozorro_contracts_winners_scraper.py` (v6.0) | Підписані договори Prozorro (Замовники + Переможці) 2023–2026 |
| `prozorro_cpv_scraper.py` (v3.0) | Скрапер за ДК 021:2015 CPV-кодами |
| `prozorro_target_search_scraper.py` (v5.0) | Пошуковий скрапер цільових освітніх тендерів |
| `prozorro_tenders_scraper.py` | High-performance multi-entity Prozorro API 2.5 скрапер |
| `prozorro_leads_processor.py` | Multi-entity lead processor (постобробка) |
| `enrich_winning_suppliers_contacts.py` (v7.0) | Реквізити/підписанти/телефони/пошти переможців з Prozorro Public API |
| `filter_prozorro_strict_profile.py` | Строгий доменний класифікатор тендерів (відсіювання нерелевантних) |
| `lookup_edrpou_emails_prozorro.py` | Прямий пошук email за ЄДРПОУ через Prozorro API |
| `parse_dk021.py` | Парсер ДК 021:2015 (CPV-класифікатор), джерело: `f451914n23.doc` |

## 🏫 Школи / ЗВО (K-12, вища освіта)

| Скрипт | Призначення |
|---|---|
| `school_scraper_engine.py` / `school_scrapers.py` | Продакшн web-scraper engine для шкільних порталів + КВЕД-датасетів |
| `run_school_scrape.py` | Запуск скрапінгу загальноосвітніх шкіл/коледжів |
| `scrape_school_portals.py` | Скрапер шкільних порталів (продакшн) |
| `school_leads_processor.py` | Дедуплікація + Excel-форматування шкільних лідів |
| `hei_leads_processor.py` | Ранжування лідів ЗВО (вища освіта) |
| `run_hei_scrape.py` / `scrape_hei_portals.py` | Скрапінг ЗВО через офіційний реєстр КВЕД + Osvita.ua/Znayshov |
| `inspect_portals_dom.py` | DOM-інспектор znayshov.com / osvita.ua / education.ua |
| `test_osvita_dom.py`, `test_osvita_parser.py`, `test_znayshov_parser.py`, `test_senior_parsers.py`, `debug_osvita_script.py` | Юніт-тести/дебаг парсерів шкільних порталів |
| `verify_school_emails.py` | MX-верифікація доставності шкільних email |

## 🤝 Партнери (книгарні/дистриб'ютори)

| Скрипт | Призначення |
|---|---|
| `run_partner_scrape.py` | Скрапер книгарень/канцтоварів/оптовиків книг |
| `enrich_partners.py` | Збагачення `partner_leads.xlsx` |
| `filter_partners.py` | Відсіювання явно нерелевантних компаній з `partner_leads.xlsx` |

## 🌍 UA-Region (email-партнерська кампанія, окрема від lead-gen шкіл)

| Скрипт | Призначення |
|---|---|
| `fast_batch_enrich_uaregion.py` (v8.2) | Паралельне збагачення email/тел за ЄДРПОУ/ІПН (не перезаписує існуюче) |
| `run_fast_uaregion_enrichment.py` (v8.1) | Запуск паралельного збагачення |
| `run_ua_region_full_scrape.py` / `run_ua_region_import.py` | Повний скрапінг/імпорт ua-region.com.ua за КВЕД |
| `enrich_winners_via_uaregion_youcontrol.py` (v8.0) | Збагачення переможців тендерів через UA-Region + YouControl |
| `enrich_youcontrol_with_uaregion.py` / `enrich_youcontrol_with_prozorro.py` | Крос-збагачення YouControl-записів |

## 🗃️ 1C (внутрішні бази контрагентів ukrmaps)

| Скрипт | Призначення |
|---|---|
| `extract_full_1c_contacts.py` / `extract_full_1c_contacts_fast.py` | Повний реєстр контактів 1C (звичайна / high-performance COMConnector версія) |
| `extract_both_1c_databases_full_contacts.py` | Обидві бази (УТП + Магазин) одночасно |
| `extract_1c_utp_magazin_split.py` | Розділення УТП/Магазин баз |
| `extract_full_magazin_contacts.py` / `extract_full_magazin_contacts_fast.py` | Контакти тільки бази "Магазин" |
| `extract_all_contacts_1c_ukrmaps.py` | 1C DWH + ukrmaps.com e-commerce контакти разом |
| `enrich_1c_from_scraped.py` | Збагачення 1C-баз email зі скрапінгу |
| `find_enrich_1c_emails.py` | Пошук/збагачення/DNS MX-верифікація email для 1C |
| `lookup_1c_registries.py` | Мульти-реєстровий пошук email (UA-Region, Clarity Project, OpenDataBot, Prozorro) |
| `classify_1c_order_types.py` | Класифікація контрагентів за типом замовлень/поведінкою закупівель |
| `probe_1c_contacts.py` | Витяг реєстру контактів через COMConnector |
| `probe_magazin_login.py` | Тест логінів до бази "Магазин" |
| `probe_metadata.py` | Проба метаданих 1C-довідників |

## 🛠️ Загальні утиліти

| Скрипт | Призначення |
|---|---|
| `build_master_email_outreach_database.py` (v2.0) | Збирає MASTER-базу розсилки з усіх джерел вище |
| `validate_emails.py` | Валідація email: regex + MX lookup |
| `safe_registry_lookup.py` | CPU-safe багатопотоковий мережевий пайплайн (Prozorro/1C lookup, connection pooling, tuple timeouts) |

---

Спільна конвенція іменування версій у докстрінгах (v1.0…v8.2) — послідовні ітерації одного скрипта під час розробки напряму 2026-07-28…2026-07-30, не seman­tic versioning пакета.
