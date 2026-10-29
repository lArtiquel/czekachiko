from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetChatMenuButton
from aiogram.types import MenuButtonWebApp

from czekachiko.__main__ import set_menu_button
from tests.fakes import make_bot


async def test_menu_button_opens_the_mini_app():
    bot, tg = make_bot()
    await set_menu_button(bot, "https://lartiquel.github.io/czekachiko/")
    (call,) = [c for c in tg.calls if isinstance(c, SetChatMenuButton)]
    assert call.chat_id is None  # the default for every private chat
    assert isinstance(call.menu_button, MenuButtonWebApp)
    assert call.menu_button.text == "Czekachiko"
    assert call.menu_button.web_app.url == "https://lartiquel.github.io/czekachiko/"


async def test_menu_button_failure_does_not_stop_the_bot(caplog):
    bot, tg = make_bot()

    async def fail(bot_, method, timeout=None):
        raise TelegramBadRequest(method=method, message="WEB_APP_URL_INVALID")

    tg.make_request = fail
    await set_menu_button(bot, "http://not-https")
    assert "menu button" in caplog.text
