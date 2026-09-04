# atlas-leadgen

Генерація лідів для ІПТ: школи, ЗВО, Prozorro, регіональні партнери.
Виділено з `atlas-industry-engine` 2026-09-04.

> **Репозиторій приватний і має таким лишатися.** Тут код, який збирає
> персональні дані (адреси й телефони закладів освіти, контакти переможців
> тендерів). Самі зібрані бази в git **не потрапляють** — див. `.gitignore`.

## Зв'язок із atlas-maps

Скрипти користуються двома модулями, які лишились у картографічному
репозиторії ([atlas-maps](https://github.com/kailung91/atlas-maps)):

- `importers.ua_region_scraper` — скрапер ua-region.com.ua;
- `models.raw_schemas` — схема запису, на якій він побудований.

Дублювати їх сюди означало б завести дві копії, що розійдуться. Шлях
додається у `atlas_bootstrap.py`; розташування береться з `ATLAS_MAPS_HOME`,
інакше припускається сусідній каталог `../atlas-industry-engine`.

```bash
# якщо картографічний репозиторій лежить не поруч
set ATLAS_MAPS_HOME=D:\path\to\atlas-maps
```

## ⚠️ Що виправлено під час переїзду

П'ять скриптів (`run_hei_scrape`, `run_partner_scrape`, `run_school_scrape`,
`run_ua_region_full_scrape`, `run_ua_region_import`) і `scrape_hei_portals`
**не запускались узагалі**: після реорганізації 19.08.2026 у `scripts/leadgen/`
їхній `sys.path` вказував на `scripts/`, а не на корінь проєкту, і всі падали з
`ModuleNotFoundError: No module named 'importers'`. Перевірено й виправлено
2026-09-04 — тепер усі шість імпортуються.

## Запуск

```bash
python scripts/leadgen/run_school_scrape.py
python scripts/leadgen/build_master_email_outreach_database.py
```

`Email/` — окремий підпроєкт (регіональні партнери за КВЕД), має власний
`requirements.txt` і власні моделі; з рештою коду не пов'язаний.
