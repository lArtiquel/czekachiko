from urllib.parse import parse_qsl, urlencode

from aiogram.utils.web_app import check_webapp_signature

from czekachiko.api.auth import MAX_AGE, user_id_from_init_data
from tests.fakes import NOW, TOKEN, sign_init_data

TS = int(NOW.timestamp())


def check(init_data: str, now: float = TS) -> int | None:
    return user_id_from_init_data(init_data, TOKEN, now)


def resign(fields: dict) -> str:
    return urlencode(fields)


def test_valid_init_data_gives_user_id():
    data = sign_init_data(user={"id": 777, "first_name": "Ola"})
    assert check_webapp_signature(TOKEN, data)  # aiogram agrees the vector is well signed
    assert check(data) == 777


def test_signature_field_is_part_of_the_signed_data():
    data = sign_init_data(extra={"signature": "abc_-xyz"})
    assert check(data) == 548


def test_tampered_field_rejected():
    fields = dict(parse_qsl(sign_init_data()))
    fields["user"] = fields["user"].replace("548", "549")
    assert check(resign(fields)) is None


def test_wrong_bot_token_rejected():
    assert check(sign_init_data(token="43:OTHER")) is None


def test_wrong_hash_rejected():
    fields = dict(parse_qsl(sign_init_data()))
    fields["hash"] = "0" * 64
    assert check(resign(fields)) is None


def test_non_ascii_hash_rejected_without_error():
    fields = dict(parse_qsl(sign_init_data()))
    fields["hash"] = "ж" * 64
    assert check(resign(fields)) is None


def test_missing_hash_rejected():
    fields = dict(parse_qsl(sign_init_data()))
    del fields["hash"]
    assert check(resign(fields)) is None


def test_duplicate_field_rejected():
    data = sign_init_data()
    assert check(data + "&user=%7B%22id%22%3A1%7D") is None


def test_stale_auth_date_rejected():
    data = sign_init_data(auth_date=TS - MAX_AGE - 1)
    assert check(data) is None
    assert check(sign_init_data(auth_date=TS - MAX_AGE + 60)) == 548


def test_future_auth_date_rejected():
    assert check(sign_init_data(auth_date=TS + 3600)) is None


def test_non_numeric_auth_date_rejected():
    fields = dict(parse_qsl(sign_init_data()))
    fields["auth_date"] = "yesterday"
    assert check(resign(fields)) is None


def test_malformed_user_json_rejected():
    assert check(sign_init_data(user="{not json")) is None


def test_user_without_numeric_id_rejected():
    assert check(sign_init_data(user={"first_name": "T"})) is None
    assert check(sign_init_data(user={"id": "548"})) is None
    assert check(sign_init_data(user={"id": True})) is None
    assert check(sign_init_data(user=[548])) is None


def test_missing_user_rejected():
    fields = dict(parse_qsl(sign_init_data()))
    del fields["user"]
    del fields["hash"]
    import hashlib
    import hmac

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    assert check(resign(fields)) is None


def test_garbage_rejected():
    for junk in ("", "hash", "a=b", "%%%", "x" * 10_000):
        assert check(junk) is None
