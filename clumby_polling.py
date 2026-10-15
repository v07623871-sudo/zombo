"""Clumby HOST: Telegram long-polling transport for the full Railway ZOMBO game.

Requires no inbound port or local PostgreSQL. All actual processing (including
Stars payments) remains in the authenticated Railway webhook endpoint.
"""
import json
import logging
import os
import random
import signal
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOG = logging.getLogger("zombo.clumby")
TOKEN = os.getenv("BOT_TOKEN", "").strip()
BACKEND = os.getenv("ZOMBO_API_URL", "https://zombo-web-production.up.railway.app").strip().rstrip("/")
SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
POLL_SECONDS = 25
STOP = False


def stop(_sig, _frame):
    global STOP
    STOP = True


def require_configuration():
    if not TOKEN or ":" not in TOKEN:
        raise RuntimeError("BOT_TOKEN must be set in Clumby HOST environment")
    if not SECRET:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET must match the Railway setting")
    parsed = urlparse(BACKEND)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("ZOMBO_API_URL must be a valid HTTPS Railway backend")
    if len(SECRET) > 256:
        raise RuntimeError("Secret token is too long")
    # Telegram expects letters, numbers, dash or underscore for the webhook secret.
    if not all(c.isalnum() or c in "-_" for c in SECRET):
        raise RuntimeError("Invalid TELEGRAM_WEBHOOK_SECRET characters")


def request_json(url, payload=None, headers=None, timeout=35):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    base_headers = {"Content-Type": "application/json", "User-Agent": "ZOMBO-Clumby-Polling/1.0"}
    base_headers.update(headers or {})
    req = Request(url, data=data, headers=base_headers, method="POST" if data else "GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        # Do not log full URLs: Telegram API URLs contain the secret bot token.
        LOG.warning("HTTP %s from %s", exc.code,
                    "Telegram" if "api.telegram.org" in url else "ZOMBO backend")
        raise


def telegram(method, body):
    # Telegram errors contain no credentials in the response. Never log URL.
    return request_json("https://api.telegram.org/bot" + TOKEN + "/" + method, body,
                        timeout=POLL_SECONDS + 15)


def forward(update):
    return request_json(
        BACKEND + "/telegram/webhook", update,
        {"X-Telegram-Bot-Api-Secret-Token": SECRET},
        timeout=32,
    )


def run():
    global STOP
    require_configuration()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("ZOMBO Clumby polling adapter starting; web game remains at %s", BACKEND)
    try:
        health = request_json(BACKEND + "/ready", timeout=12)
    except Exception as exc:
        raise RuntimeError("Railway backend /ready unavailable: " + type(exc).__name__) from exc
    if not health or not isinstance(health, dict):
        raise RuntimeError("Unexpected response from Railway /ready")

    # Polling and webhooks are mutually exclusive for ONE token.
    # drop_pending_updates=False preserves messages/payments from downtime.
    detached = telegram("deleteWebhook", {"drop_pending_updates": False})
    if not detached.get("ok"):
        raise RuntimeError("Cannot disable Telegram webhook: " +
                           str(detached.get("description", "unknown error")))
    info = telegram("getMe", {})
    if not info.get("ok"):
        raise RuntimeError("BOT_TOKEN is invalid or Telegram API is not available")
    LOG.info("Telegram bot @%s connected (polling)", info.get("result", {}).get("username", "unknown"))

    offset = None
    failures = 0
    while not STOP:
        try:
            result = telegram("getUpdates", {
                "offset": offset,
                "limit": 25,
                "timeout": POLL_SECONDS,
                "allowed_updates": ["message", "pre_checkout_query"],
            })
            if not result.get("ok"):
                message = str(result.get("description", "Telegram polling failed"))
                if "webhook" in message.lower():
                    # In case Railway restarted with webhook still enabled,
                    # reclaim transport without discarding pending updates.
                    telegram("deleteWebhook", {"drop_pending_updates": False})
                raise RuntimeError(message)
            for update in result.get("result", []):
                update_id = update["update_id"]
                if offset is not None and update_id < offset:
                    continue
                # Only acknowledge an update to Telegram after Railway reports
                # success. The backend maintains its own idempotency receipts.
                response = forward(update)
                if not isinstance(response, dict) or not response.get("ok"):
                    raise RuntimeError("ZOMBO backend rejected update " + str(update_id))
                offset = update_id + 1
                LOG.info("Update %s delivered", update_id)
            failures = 0
        except (URLError, HTTPError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            failures += 1
            LOG.warning("Temporary polling/relay failure (%s); retry %d", type(exc).__name__, failures)
            # Never crash-loop on transient networking or a restarting backend.
            time.sleep(min(60, max(2, 2 ** min(failures, 5))) + random.random())
    LOG.info("Polling shutdown requested")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        LOG.error("Configuration or startup error: %s", str(exc).replace(TOKEN, "[redacted]") if TOKEN else str(exc))
        sys.exit(1)
