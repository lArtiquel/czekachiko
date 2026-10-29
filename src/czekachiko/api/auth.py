"""Telegram Mini App initData validation. Pure: no I/O, no logging.

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

MAX_AGE = 24 * 3600
# Our clock may trail Telegram's by a few seconds; anything beyond this is "in the future".
CLOCK_SKEW = 60
MAX_LENGTH = 4096


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def user_id_from_init_data(init_data: str, bot_token: str, now: float) -> int | None:
    """The signed user's Telegram id, or None if anything is missing, forged or stale."""
    if not init_data or len(init_data) > MAX_LENGTH:
        return None
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    fields = dict(pairs)
    if len(fields) != len(pairs):  # a repeated key could smuggle a second value
        return None
    received = fields.pop("hash", None)
    if received is None:
        return None
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    expected = hmac.new(_secret(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), received.encode()):
        return None
    auth_date = fields.get("auth_date", "")
    if not (auth_date.isascii() and auth_date.isdigit()):
        return None
    age = now - int(auth_date)
    if age > MAX_AGE or age < -CLOCK_SKEW:
        return None
    try:
        user = json.loads(fields.get("user", ""))
    except ValueError:
        return None
    uid = user.get("id") if isinstance(user, dict) else None
    if type(uid) is not int or uid <= 0:
        return None
    return uid
