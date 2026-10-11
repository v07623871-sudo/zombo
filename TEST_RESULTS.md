# Проверки версии 0.9.3

- `python -m pytest -q tests` — **55 passed**, 127 предупреждений об устаревающих API в локальном Python 3.14; `node --check static/app.js` — успешно.
- Локальная Mini App в браузере с `DEMO_MODE=1` и SQLite: персонаж перемещён в Мёртвый лес, начат бой с Ползуном. После выбора головы касание портрета нанесло **15 урона в корпус**, снизило энергию **199 → 197**, обновило HP врага **45 → 30**, показало итог хода и всплывающий урон. Следующая атака кнопкой с выбранной головой нанесла **16 урона в голову**, снизила энергию **197 → 195**. Бой завершился победой после касания. Во втором бою двойное касание вызвало один ход: энергия **189 → 187**, в журнале один удар. Реальный Telegram WebView, физическое устройство и нагрузочный тест не проводились.

## Предыдущие проверки 0.9.2

- Итоговый `python -m pytest -q tests` — **55 passed**, 127 предупреждений об устаревающих API на локальном Python 3.14. Новые проверки: сортировка рейтинга по уровню, убийствам и PvP, скрытие заблокированных игроков, команды Telegram `/top`, `/quests`, `/boss`, `/raid`, `/expedition` для пустого и активного состояния.
- `node --check static/app.js` и `python -m compileall -q app.py admin.py game.py gear.py gear_market.py raids.py expeditions.py clan_wars.py story.py scripts` — успешно.
- Локальный браузер с `DEMO_MODE=1`: вручную пройдены «База → Меню → Лидеры → Арена → Назад → Меню → Назад → База», проверены группировка меню и вид кнопки «Назад». Тест проводился на локальной SQLite; настоящий Telegram BackButton и узкие физические телефоны не проверялись.

## Предыдущие проверки 0.9.1

- Перед исправлением добавленный `tests/test_boss_cycle.py` воспроизвёл ошибку: прямой `/api/boss/hit` после истечения старого цикла возвращал 400, если экран босса ещё не открывали. После исправления тест проходит: новый цикл начинается при ударе, прежняя запись урона остаётся в БД, рейтинг относится к новому циклу.
- Итоговый `python -m pytest -q tests` — **54 passed**, 127 предупреждений об устаревающих API на локальном Python 3.14.
- `node --check static/app.js` и `python -m compileall -q app.py admin.py game.py gear.py gear_market.py raids.py expeditions.py clan_wars.py story.py scripts` — успешно.

## Предыдущие проверки 0.9.0

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

## ZOMBO 0.10.0 local verification

- `python -m pytest -q tests`: **62 passed** (SQLite integration and unit tests)
- `node --check static/app.js`: passed, frontend changed minimally
- `python -m compileall -q .`: passed
- Production PostgreSQL concurrency, a scheduled backup run, and actual restore drill must be verified after deployment; local unit tests cannot certify them.
