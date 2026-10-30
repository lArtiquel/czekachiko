"""Russian copy. Labels here are also used for the public calendar."""

from czekachiko.domain import Channel, Milestone, PermitType, Purpose, Voivodeship

V, P, M, T = Voivodeship, Purpose, Milestone, PermitType

VOIV_LABELS = {
    V.dolnoslaskie: "Dolnośląskie",
    V.kujawsko_pomorskie: "Kujawsko-pomorskie",
    V.lubelskie: "Lubelskie",
    V.lubuskie: "Lubuskie",
    V.lodzkie: "Łódzkie",
    V.malopolskie: "Małopolskie",
    V.mazowieckie: "Mazowieckie",
    V.opolskie: "Opolskie",
    V.podkarpackie: "Podkarpackie",
    V.podlaskie: "Podlaskie",
    V.pomorskie: "Pomorskie",
    V.slaskie: "Śląskie",
    V.swietokrzyskie: "Świętokrzyskie",
    V.warminsko_mazurskie: "Warmińsko-mazurskie",
    V.wielkopolskie: "Wielkopolskie",
    V.zachodniopomorskie: "Zachodniopomorskie",
}

PURPOSE_LABELS = {
    P.praca: "работа",
    P.jdg: "бизнес (JDG)",
    P.studia: "учёба",
    P.rodzina: "семья",
    P.inne: "другое",
    P.blue_card: "Blue Card",
    P.staly: "постоянный побыт",
    P.rezydent_ue: "резидент ЕС",
}

PERMIT_TYPE_LABELS = {
    T.temporary: "временный побыт",
    T.permanent: "постоянный побыт",
    T.eu_resident: "резидент ЕС",
}

PERMIT_TYPE_BUTTONS = {
    T.temporary: "Временный побыт (pobyt czasowy)",
    T.permanent: "Постоянный побыт (pobyt stały)",
    T.eu_resident: "Резидент ЕС (rezydent długoterminowy UE)",
}

MILESTONE_LABELS = {
    M.filed: "подача",
    M.case_number: "номер дела",
    M.braki: "вызов на отпечатки пальцев",
    M.fingerprints: "отпечатки сданы",
    M.decision: "decyzja",
    M.card: "карта",
}

CHANNEL_LABELS = {Channel.mos: "MOS (онлайн)", Channel.paper: "Лично / почтой"}

PURPOSE_BUTTONS = {
    P.praca: "Работа (art. 114)",
    P.jdg: "Своё дело / ИП — JDG (art. 142)",
    P.studia: "Учёба",
    P.rodzina: "Семья",
    P.inne: "Другое",
    P.blue_card: "Blue Card (Niebieska Karta UE)",
    P.staly: "Постоянный побыт (pobyt stały)",
    P.rezydent_ue: "Резидент ЕС (rezydent długoterminowy UE)",
}

MILESTONE_HINTS = {
    M.filed: "когда подал wniosek",
    M.case_number: "когда пришёл номер дела (sygnatura)",
    M.braki: "когда пришёл вызов (wezwanie) на отпечатки / uzupełnienie braków",
    M.fingerprints: "когда сдал отпечатки",
    M.decision: "когда вынесли decyzję",
    M.card: "когда получил карту",
}


MESSAGES = {
    "menu_title": "🐕 <b>Czekachiko</b> подскажет, когда ждать отпечатков, decyzji и карты побыту. Считаю по анонимным делам людей в твоём воеводстве.",
    "chain_line": "обычно: в среднем {mean} дн. (мин {min}, макс {max}) (дел: {n})",
    "chain_none": "данных пока нет (дел: 0)",
    "chain_own": "{days} дн.",
    "btn_feedback": "✉️ Написать нам",
    "btn_open_app": "🚀 Открыть приложение",
    "btn_open_webapp": "🚀 Открыть Czekachiko",
    "keyboard_ready": "👇 Приложение и «Написать нам» — под полем ввода.",
    "feedback_prompt": "✉️ Напиши сообщение одним текстом, до 1000 символов: вопрос, идея или ошибка. Отвечу здесь же.",
    "feedback_sent": "✅ Сообщение передано в поддержку",
    "feedback_limit": "Можно отправить не больше 5 сообщений в час. Попробуй позже.",
    "feedback_too_long": "Слишком длинно: максимум 1000 символов.",
    "feedback_text_only": "Можно отправить только текст.",
    "feedback_admin_header": "✉️ Обратная связь #{id} · user {tg} · {ulang}",
    "feedback_reply_header": "💬 Ответ поддержки Czekachiko:",
    "feedback_delivered": "✅ Доставлено",
    "feedback_undelivered": "⚠️ Не доставлено: пользователь заблокировал бота или удалил аккаунт.",
    "feedback_not_found": "Не нашёл обращение для этого реплая.",
    "card_title": "📊 <b>Czekachiko · {purpose}</b>",
    "card_footer": "Сроки по анонимным данным людей, не официальные · @czekachiko_bot",
    "card_description": "Сроки по этапам: в среднем, мин, макс",
    "btn_open_bot": "🐕 Открыть Czekachiko",
    "case_card_title": "🐕 <b>Моё дело в Czekachiko</b>",
    "case_card_label": "Моё дело",
    "btn_cancel": "✖️ Отмена",
    "fc_title": "Прогноз: <b>{target}</b>",
    "fc_window": (
        "обычно между <b>{start}</b> и <b>{end}</b>, чаще всего около <b>{likely}</b>\n"
        "<i>по {n} завершённым делам ({scope}), которые ждали не меньше тебя</i>"
    ),
    "fc_scope_voiv": "{voiv}, {purpose}",
    "fc_scope_voiv_filed": "{voiv}, {purpose}, от даты подачи",
    "fc_scope_national": "вся Польша, {purpose} — по твоему воеводству пока мало данных",
    "fc_scope_voiv_group": "{voiv}, {group}, все основания — по основанию «{purpose}» пока мало данных",
    "fc_scope_national_group": "вся Польша, {group}, все основания — по твоему воеводству и основанию пока мало данных",
    "fc_waited_longer": (
        "ты уже ждёшь дольше, чем {x} из {y} завершённых дел в этой группе. "
        "Окно посчитать не из чего — держись 🐾"
    ),
    "fc_no_data": "Пока мало данных для прогноза. Позови знакомых добавить свои дела 🙏",
    "fc_all_done": "Все этапы пройдены — поздравляю! 🎉",
    "fc_fastest_slowest": "быстрее всех: {fastest} дн. · дольше всех: {slowest} дн.",
    "disclaimer": (
        "ℹ️ Дата в письме urzędu — не прогноз. Здесь оценка по данным людей, не официальная."
    ),
    "admin_title": "🛠 <b>Admin</b>",
    "admin_recomputed": "Пересчитано.",
    "cmd_start": "🚀 Открыть Czekachiko",
    "feedback_cancelled": "✖️ Отменено.",
    "stale_button": "Эта кнопка устарела. Открой приложение 🚀",
    "unknown_message": "🐕 Всё теперь в приложении 👇 Вопрос или идея? Нажми «✉️ Написать нам».",
    "inline_open_app": "📱 Выбрать в приложении",
    "all_poland": "Вся Польша",
    "all_bases": "{group}, все основания",
}
