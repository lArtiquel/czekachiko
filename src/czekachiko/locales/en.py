"""English copy."""

from czekachiko.domain import Channel, Milestone, PermitType, Purpose

P, M, T = Purpose, Milestone, PermitType

PURPOSE_LABELS = {
    P.praca: "work",
    P.jdg: "business (JDG)",
    P.studia: "study",
    P.rodzina: "family",
    P.inne: "other",
    P.blue_card: "Blue Card",
    P.staly: "permanent residence",
    P.rezydent_ue: "EU long-term resident",
    P.nieznane: "other / not specified",
}
PURPOSE_BUTTONS = {
    P.praca: "Work (art. 114)",
    P.jdg: "Own business — JDG (art. 142)",
    P.studia: "Study",
    P.rodzina: "Family",
    P.inne: "Other",
    P.blue_card: "Blue Card (Niebieska Karta UE)",
    P.staly: "Permanent residence (pobyt stały)",
    P.rezydent_ue: "EU long-term resident (rezydent długoterminowy UE)",
    P.nieznane: "Other / not specified",
}
PERMIT_TYPE_LABELS = {
    T.temporary: "temporary residence",
    T.permanent: "permanent residence",
    T.eu_resident: "EU long-term resident",
    T.unknown: "other / not specified",
}
PERMIT_TYPE_BUTTONS = {
    T.temporary: "Temporary residence (pobyt czasowy)",
    T.permanent: "Permanent residence (pobyt stały)",
    T.eu_resident: "EU long-term resident (rezydent długoterminowy UE)",
    T.unknown: "Other / not specified",
}
MILESTONE_LABELS = {
    M.filed: "filed",
    M.case_number: "case number",
    M.braki: "fingerprint appointment letter",
    M.fingerprints: "fingerprints given",
    M.decision: "decision",
    M.card: "card",
}
MILESTONE_HINTS = {
    M.filed: "when you filed the application",
    M.case_number: "when you got the case number (sygnatura)",
    M.braki: "when the letter (wezwanie) inviting you to give fingerprints arrived",
    M.fingerprints: "when you gave fingerprints",
    M.decision: "when the decision was issued",
    M.card: "when you collected the card",
}
CHANNEL_LABELS = {
    Channel.in_person: "In person at the office",
    Channel.post: "Post or e-Doręczenia",
    Channel.mos: "MOS (online)",
    Channel.unknown: "Method not given",
}
# Inline share cards keep the wording from before channels were split: their statistics
# cover every channel, and their text is pinned (tests/golden).
CARD_CHANNEL_LABELS = {
    Channel.in_person: "In person / by post",
    Channel.post: "In person / by post",
    Channel.mos: "MOS (online)",
    Channel.unknown: "Method not given",
}

MESSAGES = {
    "menu_title": "🐕 <b>Czekachiko</b> estimates when to expect fingerprints, the decision and your residence card, from people's anonymous cases in your voivodeship.",
    "chain_line": "typically: on average {mean} d (min {min}, max {max}) (cases: {n})",
    "chain_none": "no data yet (cases: 0)",
    "chain_own": "{days} d",
    "btn_feedback": "✉️ Contact us",
    "btn_open_app": "🚀 Open the app",
    "btn_open_webapp": "🚀 Open Czekachiko",
    "keyboard_ready": "👇 The app and Contact us are below the input field.",
    "feedback_prompt": "💬 The support chat is open. Write a question, an idea or a bug here, in as many messages as you like, with a photo or a file. While the chat is open, everything you send the bot reaches me. I'll reply here.",
    "feedback_limit": "You can send up to 20 messages per hour. Please try later.",
    "feedback_too_long": "Too long: 1000 characters maximum.",
    "feedback_text_only": "You can send text, a photo or a file.",
    "feedback_closed": "✖️ The support chat is closed. If anything else comes up, tap «✉️ Contact us».",
    "btn_close_support": "✖️ Close the support chat",
    "feedback_admin_hint": "To answer a user, reply to their message.",
    "history_empty": "No messages with this user.",
    "feedback_admin_header": "✉️ Feedback #{id} · user {tg} · {ulang}",
    "feedback_reply_header": "💬 Reply from Czekachiko support:",
    "feedback_undelivered": "⚠️ Not delivered: the user blocked the bot or deleted the account.",
    "feedback_not_found": "Couldn't find the message this reply refers to.",
    "card_title": "📊 <b>Czekachiko · {purpose}</b>",
    "card_footer": "Timelines from people's anonymous data, not official · @czekachiko_bot",
    "card_description": "Timelines per milestone: average, min, max",
    "btn_open_bot": "🐕 Open Czekachiko",
    "case_card_title": "🐕 <b>My case on Czekachiko</b>",
    "case_card_label": "My case",
    "btn_cancel": "✖️ Cancel",
    "fc_title": "Forecast: <b>{target}</b>",
    "fc_window": (
        "usually between <b>{start}</b> and <b>{end}</b>, most often around <b>{likely}</b>\n"
        "<i>from {n} completed cases ({scope}) that waited at least as long as you</i>"
    ),
    "fc_scope_voiv": "{voiv}, {purpose}",
    "fc_scope_voiv_filed": "{voiv}, {purpose}, from the filing date",
    "fc_scope_national": "all of Poland, {purpose}: too little data for your voivodeship yet",
    "fc_scope_voiv_group": "{voiv}, {group}, all bases: too little data for {purpose} yet",
    "fc_scope_national_group": "all of Poland, {group}, all bases: too little data for your voivodeship and basis yet",
    "fc_waited_longer": (
        "you've already waited longer than {x} of {y} completed cases in this group. "
        "There's nothing left to compute a window from. Hang in there 🐾"
    ),
    "fc_no_data": "Not enough data for a forecast yet. Ask friends to add their cases 🙏",
    "fc_all_done": "All milestones done. Congratulations! 🎉",
    "fc_fastest_slowest": "fastest: {fastest} d · slowest: {slowest} d",
    "disclaimer": (
        "ℹ️ The date in the office's letter is not a forecast. This is an estimate from "
        "people's data, not official."
    ),
    "admin_title": "🛠 <b>Admin</b>",
    "admin_recomputed": "Recomputed.",
    "admin_calendar_queued": "Calendar events queued: {n}.",
    "cmd_start": "🚀 Open Czekachiko",
    "stale_button": "This button is outdated. Open the app 🚀",
    "unknown_message": "🐕 Everything is in the app now 👇 A question or an idea? Tap «✉️ Contact us».",
    "inline_open_app": "📱 Choose in the app",
    "all_poland": "All of Poland",
    "all_bases": "{group}, all bases",
}
