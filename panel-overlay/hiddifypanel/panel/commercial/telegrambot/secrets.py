import os
from pathlib import Path

from hiddifypanel.models import ConfigEnum, hconfig


SECRETS_FILE = Path("/etc/hiddify-panel/panel-secrets.env")


def _env_or_file(*keys: str) -> str:
    for key in keys:
        value = (os.environ.get(key, "") or "").strip()
        if value:
            return value

    try:
        with SECRETS_FILE.open("r", encoding="utf-8") as fh:
            rows: dict[str, str] = {}
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                rows[key.strip()] = value.strip()
        for key in keys:
            value = rows.get(key, "").strip()
            if value:
                return value
    except OSError:
        pass
    return ""


def telegram_bot_token() -> str:
    return (
        _env_or_file("HIDDIFY_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
        or (hconfig(ConfigEnum.telegram_bot_token) or "")
    ).strip()


def telegram_payment_provider_token() -> str:
    return (
        _env_or_file(
            "HIDDIFY_TELEGRAM_PAYMENT_PROVIDER_TOKEN",
            "TELEGRAM_PAYMENT_PROVIDER_TOKEN",
        )
        or (hconfig(ConfigEnum.telegram_payment_provider_token) or "")
    ).strip()
