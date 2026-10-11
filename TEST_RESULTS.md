# Проверки версии 0.9.0

- После добавления дальних экспедиций: `python -m pytest -q tests` — **53 passed**, 127 предупреждений об устаревающих API на локальном Python 3.14. Новые четыре API-теста проверяют 12-часовой цикл, роли и права, успешную/неудачную выдачу, срок набора, передачу лидерства, полный склад и защиту от повторного начисления.
- `node --check static/app.js` — успешно. `python -m compileall -q app.py admin.py game.py gear.py gear_market.py raids.py expeditions.py clan_wars.py story.py scripts` — успешно.
- `python scripts/migrate.py` на локальной пустой SQLite — созданы `expedition_members`, `expedition_runs`, `payment_reviews`, `star_invoices` (остальные таблицы были созданы при запуске предыдущих проверок). Миграция на копии PostgreSQL не запускалась.

## Предыдущие проверки 0.8.2

- Исходный запуск `python -m pytest -q tests` на локальном Python 3.14 сначала остановился при сборе из-за перезаписи `sys.modules` в `tests/test_gear_market.py`. После исправления: **42 passed**.
- После изменений 0.8.2: `python -m pytest -q tests` — **49 passed**, 113 предупреждений об устаревающих API FastAPI/Starlette/Python 3.14. Критических ошибок нет.
- `node --check static/app.js` — успешно.
- `python -m compileall -q app.py admin.py game.py gear.py gear_market.py raids.py clan_wars.py story.py scripts` — успешно.
- Тесты проверяют права админки, журнал и идемпотентность, сохранность старой строки при миграции, истечение рейда, новый и старый форматы счетов Stars, платёж на проверку и защиту от повторного начисления, завершение PvP по таймеру, API-покупку уникального снаряжения и прежние игровые сценарии.
- `GET /health` проверен в существующем API-тесте, `GET /ready` — через TestClient на локальной SQLite. Живой Telegram, PostgreSQL/Railway, `pg_dump`/`pg_restore` с настоящей БД, интерфейс на устройстве и реальные платежи не проверялись. Production не изменялся.
- Локальные зависимости ставились на Python 3.14 с `psycopg[binary]` 3.3.6, потому что закреплённый в `requirements.txt` 3.2.6 не предоставляет wheel для Python 3.14. Production рассчитан на Python 3.11 и его зависимости не менялись.
