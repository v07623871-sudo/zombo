# ZOMBO для Clumby HOST (polling)

Clumby не поддерживает FastAPI/Uvicorn и PostgreSQL. Поэтому в ZIP для Clumby находятся только Telegram polling-процесс `main.py`, `clumby_polling.py`, минимальный `requirements.txt` и шаблон настройки. **Это не локальная копия игры**. Сама игра, Mini App, магазин Stars, админка, база PostgreSQL и фоновые задания работают на Railway.

## Параметры Clumby

- Файл запуска: `main.py` (или команда `python main.py`)
- Версия Python: 3.10+
- `BOT_TOKEN`: тот же актуальный токен, что использует Railway
- `ZOMBO_API_URL=https://zombo-web-production.up.railway.app`
- `TELEGRAM_WEBHOOK_SECRET`: в точности тот же секрет, что используется на Railway для `/telegram/webhook`
- Никакой веб-порт и PostgreSQL на Clumby не нужны.

## Параметры Railway

В сервисе `zombo-web` надо установить `TELEGRAM_UPDATES_TRANSPORT=external_polling` и задеплоить **версию ZOMBO 0.42**. `BOT_TOKEN`, `PUBLIC_URL`, `TELEGRAM_WEBHOOK_SECRET` и DATABASE_URL на Railway сохраняются прежними. Ничего не стирайте.

После этого загрузить отдельный Clumby ZIP, заполнить переменные и запустить `main.py`. При запуске адаптер вызовет `deleteWebhook(drop_pending_updates=false)` и перейдёт на `getUpdates`. Не запускайте вторую копию polling-бота с тем же токеном.

## Как проверить

1. В логах Clumby: `Telegram bot @... connected (polling)`, без повторных перезапусков.
2. В Telegram: `/start`, `/profile`, `/admin`, открытие Mini App.
3. Проверить заявку Stars на отдельном тестовом платеже. `pre_checkout_query` и `successful_payment` пересылаются в Railway.
4. В Railway: `/ready` HTTP 200, данные сохранены, webhook не переустанавливается после рестартов.

Если Clumby остановился, Telegram накопит необработанные обновления. Адаптер подтвердит Telegram только полученные Railway успешные обновления, а сервер ZOMBO ведёт собственный журнал `update_id` для защиты от повторного начисления.

## Важно: новый токен

Ранее в переписке был опубликован бот-токен. Его надо **перевыпустить через BotFather** и заменить на обоих сервисах. Не класть токен и секрет в ZIP, GitHub или общий чат: любой получивший архив сможет управлять ботом.

## Чего Clumby не сможет

Мини-приложение, игровые API, PostgreSQL и админский веб-интерфейс по-прежнему требуют Railway. Если Railway отключить, Clumby не сможет обслуживать игру или платежи. Для полностью автономного переноса нужен VPS с постоянным HTTP и PostgreSQL, а не polling-only hosting.
