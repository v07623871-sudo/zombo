# Что лежит в полном GitHub ZIP

Загрузка **актуальных исходников и этих инструкций одним ZIP**:

https://github.com/v07623871-sudo/zombo/archive/refs/heads/codex-handoff.zip

Точка входа: `app.py`. Это одновременно FastAPI и Telegram Bot webhook (в том числе `/telegram/webhook`, `/start`, `/daily`, `/profile`, `/help`, `/skills`, `/map`, `/enemies`, `/bag`, `/clan`, `/story`, успешные оплаты Telegram Stars).

Игровые модули: `game.py`, `models.py`, `clan_wars.py`, `raids.py`, `gear.py`, `gear_market.py`, `story.py`.

Мини-приложение: `static/index.html`, `static/app.js`, `static/style.css`, `static/mobs/*.svg`.

Инфраструктура: `requirements.txt`, `railway.json`, `Procfile`, `.gitignore`, `.env.example`, `README.md`.

Тесты: все файлы внутри `tests/`.

**Важно**: текущий код и инструкции находятся в `codex-handoff`; сам production `main` не затронут добавлением документации. В полное скачивание ветки из GitHub входят все файлы, не только документация.