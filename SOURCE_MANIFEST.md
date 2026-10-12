# Состав ZOMBO_CODEX_COMPLETE.zip

> Историческая опись 0.9.3. Текущий архив содержит весь checkout версии 0.21 (исходная 0.16 и последующие изменения): `app.py` с Telegram-ботом, все игровые модули, `static/`, `tests/`, `scripts/`, `.github/workflows/`, `ops/backup/` и актуальные четыре отчёта. Локальные БД, `.env`, `.git` и кеши исключены.

Полный исходный код версии 0.9.3: `app.py` (FastAPI, весь Telegram-бот и webhook), `admin.py`, `models.py`, `game.py`, `clan_wars.py`, `raids.py`, `expeditions.py`, `gear.py`, `gear_market.py`, `story.py`.

Mini App: `static/index.html`, `static/app.js`, `static/style.css` и все исходные `static/mobs/*.svg`.

Инфраструктура: `requirements.txt`, `railway.json`, `Procfile`, `.gitignore`, `.env.example`; инструменты миграции и резервного копирования в `scripts/`.

Все исходные и новые тесты — в `tests/`. Отчёты: `CHANGELOG_DONE.md`, `TODO_REMAINING.md`, `TEST_RESULTS.md`, `DEPLOY_NOTES.md`, `README.md`. Исходные документы передачи оставлены для контекста. Реальные секреты и базы данных в архив не включены.
