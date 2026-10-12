# Проверки текущего пакета

Исходник: GitHub `main` `c0b0ce4bdb45cd00debd7a88a5db01a453abb7de` (версия 0.16). Работа велась в отдельной локальной ветке `codex/zombo-0.17-reliability`.

| Проверка | Результат |
|---|---|
| `python -m pytest -q tests` до изменений | 87 passed, Python 3.14.3 |
| `python -m pytest -q tests` после изменений | 113 passed, 165 deprecation warnings |
| `python -m compileall -q app.py game.py gear.py clan_missions.py security.py notifications.py world_events.py encounters.py raids.py clan_wars.py admin.py scripts tests` | Успешно |
| `node --check static/app.js` | Успешно |
| `git diff --check` | Успешно |
| `python scripts/simulate_balance.py --wins 25000 --seed 20261012` | Успешно: 4 сценария, 100 000 смоделированных побед |

`tests/test_encounters.py` дополнительно проверяет новые решения, зацепки между сценами, фильтр локации, расход ресурсов и запрет повторной награды. При seed 20261012 симуляция дала в Мёртвом лесу 47.68 XP, 25.80 крышки и 7.98% выпадения экипировки на победу за солдата; в Красной пустоши — 189.08 XP, 90.31 крышки, 17.53% экипировки и 7.98% элитных целей. Это валовые величины при каждой победе, без смерти, затрат энергии, налогов, рынка и первого открытия вида; баланс игры не менялся.

`tests/test_resource_ledger.py` проверяет начальные ресурсы, ежедневную награду, движения предметов и уникальной экипировки, общий ID операции, откат транзакции, отказ при повторе стабильного ID и права/фильтры админки. Тесты платежей и админки дополнительно сверяют запись Stars и ручной выдачи по их стабильным ID; тест рынка сверяет покупку с обеих сторон. Проверки выполнены на SQLite через приложение, не на живой PostgreSQL. Старые движения до установки 0.21 не восстановлены.

`tests/test_market_api.py::test_reciprocal_barter_preserves_both_inventories` проверяет две встречные сделки и сохранение ресурсов через FastAPI и SQLite. Пять тестов в `tests/test_elite_enemies.py` проверяют элитные модификаторы и выдачу наград. Два теста в `tests/test_raid_war_notifications.py` проверяют очередь рейда и КВ. `tests/test_clan_missions.py` и `tests/test_season_api.py` проверяют сезон и однократную выплату; `tests/test_admin.py` — доступ к диагностике. Пять тестов в `tests/test_migrate.py` проверяют сохранение игрока, журнал версий, режим без записи и отказ при потере колонок, ключей, индексов или зарегистрированной таблицы. `scripts/verify_migration_pg.py` и `scripts/verify_concurrency_pg.py` подключены к CI, но их **не удалось выполнить локально**, поскольку на этой машине нет отдельного PostgreSQL или Docker. Результат будущего CI запуска требуется проверить до переноса в production. Настоящие Telegram Android/iOS, платежи Stars, Railway и живые данные не проверялись и не изменялись.
