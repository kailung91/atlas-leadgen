"""Спільний bootstrap шляхів для скриптів atlas-leadgen.

НАВІЩО. Lead-gen користується двома модулями, які лишились у картографічному
репозиторії: `importers.ua_region_scraper` (скрапер ua-region) і `models`
(схеми, на яких він побудований). Дублювати їх сюди означало б завести дві
копії, що розійдуться; тому шлях до сусіднього репозиторію додається явно.

⚠️ ЩО ЦЕ ВИПРАВЛЯЄ. До переїзду п'ять скриптів робили
`sys.path.insert(0, Path(__file__).parent.parent)`, що після реорганізації
19.08.2026 вказувало на `scripts/`, а не на корінь проєкту. Усі п'ять падали з
`ModuleNotFoundError: No module named 'importers'` — перевірено 2026-09-04.

Розташування картографічного репозиторію береться з `ATLAS_MAPS_HOME`, інакше
припускається сусідній каталог.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ATLAS_MAPS = Path(os.environ.get("ATLAS_MAPS_HOME",
                                 ROOT.parent / "atlas-industry-engine")).resolve()

for _p in (ROOT, ATLAS_MAPS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

if not (ATLAS_MAPS / "importers").is_dir():
    raise SystemExit(
        f"Не знайдено картографічний репозиторій за шляхом {ATLAS_MAPS}.\n"
        f"Вкажіть його змінною середовища ATLAS_MAPS_HOME."
    )
