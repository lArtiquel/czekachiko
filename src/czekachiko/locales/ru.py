"""Russian copy. Labels here are also used for the public calendar."""

from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship

V, P, M = Voivodeship, Purpose, Milestone

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
    P.praca: "art. 114",
    P.jdg: "art. 142",
    P.studia: "учёба",
    P.rodzina: "семья",
    P.inne: "другое",
}

MILESTONE_LABELS = {
    M.filed: "подача",
    M.case_number: "номер дела",
    M.braki: "wezwanie о brakach",
    M.fingerprints: "отпечатки",
    M.decision: "decyzja",
    M.card: "карта",
}

CHANNEL_LABELS = {Channel.mos: "MOS (онлайн)", Channel.paper: "Лично / почтой"}

PURPOSE_BUTTONS = {
    P.praca: "Работа (art. 114)",
    P.jdg: "Działalność gospodarcza (art. 142)",
    P.studia: "Учёба",
    P.rodzina: "Семья",
    P.inne: "Другое",
}

MILESTONE_HINTS = {
    M.filed: "когда подал wniosek",
    M.case_number: "когда пришёл номер дела (sygnatura)",
    M.braki: "когда пришло wezwanie о brakach formalnych",
    M.fingerprints: "когда сдал отпечатки",
    M.decision: "когда вынесли decyzję",
    M.card: "когда получил карту",
}

MONTHS = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

MESSAGES = {
    "menu_title": "🐕 <b>Czekachiko</b> подскажет, когда ждать отпечатков, decyzji и карты побыту. Считаю по анонимным делам людей в твоём воеводстве.",
    "btn_add": "➕ Добавить дело",
    "btn_cases": "📂 Мои дела",
    "btn_stats": "📊 Сроки по воеводствам",
    "btn_calendar": "📅 Календарь",
    "btn_settings": "⚙️ Настройки",
    "btn_share": "📣 Поделиться ботом",
    "share_text": "Когда придёт karta pobytu? 🐕 Czekachiko прогнозирует сроки по воеводствам на основе анонимных данных людей. Добавь своё дело — прогноз станет точнее для всех.",
    "share_prompt": "Отправь Czekachiko друзьям или в чат 👇",
    "chain_line": "обычно: в среднем {mean} дн. (мин {min}, макс {max}) (дел: {n})",
    "chain_none": "данных пока нет (дел: 0)",
    "chain_own": "{days} дн.",
    "chain_title": "От подачи до каждого этапа",
    "btn_help": "❓ Как это работает",
    "btn_back": "⬅️ Назад",
    "btn_menu": "🏠 Меню",
    "btn_cancel": "✖️ Отмена",
    "privacy": "🔒 Храню только Telegram ID, воеводство, цель и даты этапов. В публичный календарь этапы попадают анонимно. Удалить всё — ⚙️ Настройки.",
    "help": "❓ <b>Как это работает</b>\n\nДобавь своё дело и отмечай этапы. По всем делам я считаю, сколько обычно длится каждый шаг в твоём воеводстве, и показываю прогноз. Чем больше дел — тем точнее. Это не официальная информация urzędu.",
    "cases_title": "📂 <b>Мои дела</b>",
    "cases_empty": "У тебя пока нет дел. Добавь первое — это займёт минуту.",
    "case_limit": "Можно вести не больше 5 дел. Удали одно из старых, чтобы добавить новое.",
    "ask_voiv": "Шаг 1/4. В каком воеводстве подано дело?",
    "ask_purpose": "Шаг 2/4. Цель пребывания?",
    "ask_channel": "Шаг 3/4. Как подавал?",
    "ask_filed": "Шаг 4/4. Дата подачи wniosku — выбери день в календаре или напиши дату (ДД.ММ.ГГГГ).",
    "ask_more": (
        "Дело сохранено ✅\n\nЧто уже произошло? Отметь пройденные этапы — или нажми «Готово»."
    ),
    "btn_done": "✅ Готово",
    "ask_milestone_date": "📅 {milestone}: {hint}. Выбери день или напиши дату (ДД.ММ.ГГГГ).",
    "btn_today": "Сегодня",
    "btn_yesterday": "Вчера",
    "btn_clear_date": "🗑 Убрать дату",
    "err_future": "Эта дата ещё не наступила. Выбери прошедший день.",
    "err_before_2015": "Дата подачи не может быть раньше 2015 года.",
    "err_before_filed": "Этап не может быть раньше даты подачи.",
    "err_order": "Порядок этапов нарушен: отпечатки → decyzja → карта.",
    "err_filed_missing": "Сначала нужна дата подачи.",
    "err_not_date": "Это не похоже на дату. Выбери день в календаре или напиши ДД.ММ.ГГГГ.",
    "err_use_buttons": "Пожалуйста, выбери вариант кнопкой 👇",
    "milestones_title": "Этапы",
    "fc_title": "Прогноз: <b>{target}</b>",
    "fc_window": (
        "обычно между <b>{start}</b> и <b>{end}</b>, чаще всего около <b>{likely}</b>\n"
        "<i>по {n} завершённым делам ({scope}), которые ждали не меньше тебя</i>"
    ),
    "fc_scope_voiv": "{voiv}, {purpose}",
    "fc_scope_voiv_filed": "{voiv}, {purpose}, от даты подачи",
    "fc_scope_national": "вся Польша, {purpose} — по твоему воеводству пока мало данных",
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
    "btn_mark": "✏️ Отметить этап",
    "btn_delete_case": "🗑 Удалить дело",
    "pick_milestone": "Какой этап отметить или исправить?",
    "confirm_delete_case": "Удалить это дело? Его данные исчезнут из статистики и календаря.",
    "btn_yes_delete": "🗑 Да, удалить",
    "btn_no": "Нет",
    "deleted": "Удалено.",
    "stats_pick_voiv": "📊 Выбери воеводство:",
    "stats_pick_purpose": "Цель пребывания:",
    "stats_title": "📊 <b>{voiv} · {purpose}</b>",
    "stats_row": "{from_} → {to}: {p10}–{p90} дн., медиана {median} <i>({n} дел)</i>",
    "stats_row_thin": "{from_} → {to}: мало данных <i>({n} дел)</i>",
    "stats_no_rows": "По этой группе пока нет данных. Добавь своё дело — будешь первым 🐕",
    "who_fp": "🖐 Сейчас на отпечатки вызывают подавшихся ≈ {span}.",
    "who_dec": "📨 Decyzje сейчас получают подавшиеся ≈ {span}.",
    "btn_other_voiv": "Другое воеводство",
    "btn_other_purpose": "Другая цель",
    "settings_title": "⚙️ <b>Настройки</b>",
    "btn_lang": "🌐 Язык: Русский → English",
    "btn_reminders": "🔔 Напоминания: {state}",
    "state_on": "вкл",
    "state_off": "выкл",
    "reminders_note": "Напоминания пока не отправляются: бот пишет только в ответ на твои действия.",
    "btn_delete_all": "🗑 Удалить все мои данные",
    "confirm_delete_all": "Удалить все твои дела и настройки? Это нельзя отменить.",
    "all_deleted": "Все твои данные удалены. Если захочешь вернуться — /start.",
    "calendar_text": (
        "📅 Публичный календарь всех анонимных событий: подачи, вызовы на отпечатки, decyzje.\n"
        "В событиях только воеводство, цель, этап и месяц подачи."
    ),
    "calendar_soon": "📅 Публичный календарь скоро появится.",
    "btn_open_calendar": "🔗 Открыть Google-календарь",
    "outlier": (
        "🤔 Обычно в {voiv} от этапа «{from_}» до «{to}» проходит {p10}–{p90} дней, "
        "а у тебя выходит {value}.\n\nПроверь, пожалуйста, даты: от этого зависит точность "
        "прогноза для всех."
    ),
    "btn_outlier_ok": "✅ Всё верно",
    "btn_outlier_fix": "✏️ Исправить",
    "saved": "Сохранено ✅",
    "admin_title": "🛠 <b>Admin</b>",
    "admin_recomputed": "Пересчитано.",
    "lang_changed": "Язык: русский 🇷🇺",
    "cmd_start": "🏠 Главное меню",
    "cmd_cases": "📂 Мои дела",
    "cmd_add": "➕ Добавить дело",
    "cmd_stats": "📊 Сроки по воеводствам",
    "cmd_calendar": "📅 Публичный календарь",
    "cmd_settings": "⚙️ Настройки",
    "cmd_help": "❓ Как это работает",
    "cmd_cancel": "✖️ Прервать текущий шаг",
}
