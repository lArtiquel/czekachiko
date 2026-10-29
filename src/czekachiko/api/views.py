"""Route handlers. Every case and document is reached through repo.get_case (owner check).

Writes go through the same repo functions as the bot, so aggregates recompute and the
calendar outbox fills exactly as they do there.
"""

from datetime import date

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from czekachiko import documents, share
from czekachiko.api.app import CLOCK, SESSION, TG_ID, USER, ApiError, read_json
from czekachiko.api.payloads import (
    CLIENT_TOKEN,
    case_json,
    chain_json,
    documents_json,
    forecast_json,
    parse_day,
    parse_enum,
    span_json,
)
from czekachiko.dates import validate_milestones
from czekachiko.db import repo
from czekachiko.db.models import Case
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.forecasting import case_forecast, find_outlier, who_now_spans
from czekachiko.i18n import LOCALES, loc, voiv_label
from czekachiko.ui.screens import calendar_url

routes = web.RouteTableDef()
M = Milestone
CASE = r"/api/cases/{case_id:\d{1,9}}"
DOC = CASE + r"/documents/{doc_id:\d{1,9}}"


def respond(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def invalid(**fields: str) -> ApiError:
    return ApiError(422, "invalid", fields=fields)


def not_found() -> ApiError:
    return ApiError(404, "not_found")


def today(request: web.Request) -> date:
    return request.app[CLOCK]()


async def owned_case(request: web.Request) -> Case:
    case_id = int(request.match_info["case_id"])
    case = await repo.get_case(request[SESSION], request[TG_ID], case_id)
    if case is None:
        raise not_found()
    return case


async def case_detail(s: AsyncSession, case: Case, day: date) -> dict:
    docs = await repo.list_docs(s, case)
    chain = await repo.chain_aggregates(s, case.voivodeship, case.purpose)
    return {
        **case_json(case, docs),
        "chain": chain_json(chain, case.dates()),
        "forecast": forecast_json(await case_forecast(s, case, day)),
        "documents": documents_json(case, docs),
    }


async def detail_response(request: web.Request, case: Case, status: int = 200) -> web.Response:
    s = request[SESSION]
    if request.method not in ("GET", "HEAD"):
        # Release the write's advisory locks before the read-only detail queries run.
        await s.commit()
    return respond(await case_detail(s, case, today(request)), status)


# --- health and profile ----------------------------------------------------------------


def user_json(user) -> dict:
    return {"tg_id": user.tg_id, "lang": user.lang, "reminders": user.reminders}


@routes.get("/api/health")
async def health(request: web.Request) -> web.Response:
    return respond({"ok": True})


@routes.get("/api/me")
async def get_me(request: web.Request) -> web.Response:
    return respond(user_json(request[USER]))


@routes.patch("/api/me")
async def patch_me(request: web.Request) -> web.Response:
    body = await read_json(request)
    if "lang" in body:
        if not isinstance(body["lang"], str) or body["lang"] not in LOCALES:
            raise invalid(lang="invalid")
        await repo.set_lang(request[SESSION], request[TG_ID], body["lang"])
    return respond(user_json(request[USER]))


@routes.delete("/api/me")
async def delete_me(request: web.Request) -> web.Response:
    """Cases, documents and feedback; the content-free feedback rate log stays."""
    await repo.delete_user(request[SESSION], request[TG_ID])
    return web.Response(status=204)


@routes.get("/api/meta")
async def meta(request: web.Request) -> web.Response:
    lang = request.query.get("lang") or request[USER].lang
    if lang not in LOCALES:
        raise invalid(lang="invalid")
    L = loc(lang)
    return respond(
        {
            "voivodeships": [{"code": v.value, "label": voiv_label(v)} for v in Voivodeship],
            "purposes": [
                {"code": p.value, "label": L.PURPOSE_LABELS[p], "button": L.PURPOSE_BUTTONS[p]}
                for p in Purpose
            ],
            "channels": [{"code": c.value, "label": L.CHANNEL_LABELS[c]} for c in Channel],
            "milestones": [
                {"code": m.value, "label": L.MILESTONE_LABELS[m], "hint": L.MILESTONE_HINTS[m]}
                for m in M
            ],
            "checklists": {
                p.value: [
                    {"code": c, "name": documents.doc_name(c)} for c in documents.checklist(p)
                ]
                for p in Purpose
            },
            "limits": {
                "max_cases": repo.MAX_CASES,
                "max_custom_docs": documents.MAX_CUSTOM,
                "max_doc_name": documents.MAX_NAME,
            },
        }
    )


# --- cases -----------------------------------------------------------------------------


@routes.get("/api/cases")
async def list_cases(request: web.Request) -> web.Response:
    s = request[SESSION]
    cases = await repo.list_cases(s, request[TG_ID])
    return respond([case_json(c, await repo.list_docs(s, c)) for c in cases])


@routes.post("/api/cases")
async def create_case(request: web.Request) -> web.Response:
    body = await read_json(request)
    errors: dict[str, str] = {}
    voiv = parse_enum(Voivodeship, body.get("voivodeship"))
    purpose = parse_enum(Purpose, body.get("purpose"))
    channel = parse_enum(Channel, body.get("channel"))
    for name, value in (("voivodeship", voiv), ("purpose", purpose), ("channel", channel)):
        if value is None:
            errors[name] = "invalid"
    filed = parse_day(body.get("filed"), today(request))
    if filed is None:
        errors["filed"] = "not_date"
    elif codes := validate_milestones({M.filed: filed}, today(request)):
        errors["filed"] = codes[0]
    token = body.get("client_token")
    if not isinstance(token, str) or not CLIENT_TOKEN.match(token):
        errors["client_token"] = "invalid"
    if errors:
        raise invalid(**errors)
    s = request[SESSION]
    try:
        case = await repo.create_case(s, request[TG_ID], voiv, purpose, channel, filed, token)
    except repo.TooManyCases:
        raise ApiError(409, "too_many_cases") from None
    except repo.TokenConflict:
        raise invalid(client_token="taken") from None
    return respond(case_json(case, await repo.list_docs(s, case)), 201)


@routes.get(CASE)
async def get_case(request: web.Request) -> web.Response:
    return await detail_response(request, await owned_case(request))


@routes.delete(CASE)
async def delete_case(request: web.Request) -> web.Response:
    await repo.delete_case(request[SESSION], await owned_case(request))
    return web.Response(status=204)


# --- milestones ------------------------------------------------------------------------


def path_milestone(request: web.Request) -> Milestone:
    milestone = parse_enum(Milestone, request.match_info["milestone"])
    if milestone is None:
        raise not_found()
    return milestone


@routes.put(CASE + "/milestones/{milestone}")
async def put_milestone(request: web.Request) -> web.Response:
    case = await owned_case(request)
    milestone = path_milestone(request)
    body = await read_json(request)
    confirm = body.get("confirm_outlier", False)
    if not isinstance(confirm, bool):
        raise invalid(confirm_outlier="invalid")
    day = parse_day(body.get("date"), today(request))
    if day is None:
        raise ApiError(422, "invalid", codes=["not_date"])
    dates = {M(k): v for k, v in case.dates().items()} | {milestone: day}
    if codes := validate_milestones(dates, today(request)):
        raise ApiError(422, "invalid", codes=codes)
    s = request[SESSION]
    outlier = await find_outlier(s, case, dates, milestone)
    if outlier is not None and not confirm:
        a, b, value, typical = outlier
        raise ApiError(
            409,
            "outlier",
            typical={"p10": round(typical.p10), "p90": round(typical.p90)},
            value=value,
            **{"from": a.value, "to": b.value},
        )
    await repo.set_milestone(s, case, milestone, day, confirmed_outlier=outlier is not None)
    return await detail_response(request, case)


@routes.delete(CASE + "/milestones/{milestone}")
async def delete_milestone(request: web.Request) -> web.Response:
    case = await owned_case(request)
    milestone = path_milestone(request)
    if milestone == M.filed:
        raise ApiError(422, "invalid", codes=["filed_missing"])
    if milestone in case.dates():
        await repo.clear_milestone(request[SESSION], case, milestone)
    return await detail_response(request, case)


# --- documents -------------------------------------------------------------------------


def doc_date_error(value, case: Case, day: date) -> tuple[date | None, str | None]:
    """A document date (None un-ticks) and the error code, if any, under the bot's rules."""
    if value is None:
        return None, None
    d = parse_day(value, day)
    if d is None:
        return None, "not_date"
    return d, documents.date_error(d, case.dates()[M.filed], day)


def doc_name_error(value) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "invalid"
    return documents.clean_name(value)


async def owned_doc(request: web.Request, case: Case):
    doc = await repo.get_custom_doc(request[SESSION], case, int(request.match_info["doc_id"]))
    if doc is None:
        raise not_found()
    return doc


@routes.put(CASE + "/documents/std/{code}")
async def put_standard_doc(request: web.Request) -> web.Response:
    case = await owned_case(request)
    code = request.match_info["code"]
    if code not in documents.checklist(case.purpose):
        raise not_found()
    body = await read_json(request)
    if "date" not in body:
        raise invalid(date="required")
    d, error = doc_date_error(body["date"], case, today(request))
    if error:
        raise invalid(date=error)
    await repo.set_standard_doc(request[SESSION], case, code, d)
    return await detail_response(request, case)


@routes.post(CASE + "/documents")
async def add_own_doc(request: web.Request) -> web.Response:
    case = await owned_case(request)
    body = await read_json(request)
    name, name_error = doc_name_error(body.get("name"))
    d, date_error = doc_date_error(body.get("date"), case, today(request))
    if errors := {k: v for k, v in (("name", name_error), ("date", date_error)) if v}:
        raise invalid(**errors)
    try:
        await repo.add_custom_doc(request[SESSION], case, name, d)
    except repo.TooManyDocs:
        raise ApiError(409, "too_many_docs") from None
    return await detail_response(request, case, 201)


@routes.patch(DOC)
async def patch_own_doc(request: web.Request) -> web.Response:
    case = await owned_case(request)
    doc = await owned_doc(request, case)
    body = await read_json(request)
    name, name_error = doc_name_error(body["name"]) if "name" in body else (None, None)
    d, date_error = (
        doc_date_error(body["date"], case, today(request)) if "date" in body else (None, None)
    )
    if errors := {k: v for k, v in (("name", name_error), ("date", date_error)) if v}:
        raise invalid(**errors)
    s = request[SESSION]
    if "name" in body:
        await repo.rename_custom_doc(s, doc, name)
    if "date" in body:
        await repo.set_doc_date(s, doc, d)
    return await detail_response(request, case)


@routes.delete(DOC)
async def delete_own_doc(request: web.Request) -> web.Response:
    case = await owned_case(request)
    await repo.delete_custom_doc(request[SESSION], await owned_doc(request, case))
    return await detail_response(request, case)


# --- statistics, calendars, sharing ----------------------------------------------------


@routes.get("/api/stats")
async def stats(request: web.Request) -> web.Response:
    voiv = parse_enum(Voivodeship, request.query.get("voivodeship"))
    purpose = parse_enum(Purpose, request.query.get("purpose"))
    errors = {k: "invalid" for k, v in (("voivodeship", voiv), ("purpose", purpose)) if v is None}
    if errors:
        raise invalid(**errors)
    s = request[SESSION]
    chain = await repo.chain_aggregates(s, voiv, purpose)
    fp, dec = await who_now_spans(s, voiv, purpose, today(request))
    return respond(
        {
            "chain": chain_json(chain),
            "who_now": {"fingerprints": span_json(fp), "decision": span_json(dec)},
        }
    )


@routes.get("/api/calendars")
async def calendars(request: web.Request) -> web.Response:
    links = await repo.calendar_links(request[SESSION])
    return respond(
        [
            {"voivodeship": v.value, "label": voiv_label(v), "url": calendar_url(links[v.value])}
            for v in Voivodeship
            if v.value in links
        ]
    )


@routes.get(r"/api/share/case/{case_id:\d{1,9}}")
async def share_case(request: web.Request) -> web.Response:
    case = await owned_case(request)  # the inline card resolves only for its owner, too
    return respond({"query": f"c:{case.id}"})


@routes.get("/api/share/stats")
async def share_stats(request: web.Request) -> web.Response:
    purpose = parse_enum(Purpose, request.query.get("purpose"))
    names = request.query.get("voivodeships", "").split(",")
    voivs = list(dict.fromkeys(parse_enum(Voivodeship, n) for n in names))
    errors = {}
    if purpose is None:
        errors["purpose"] = "invalid"
    if None in voivs or not voivs:
        errors["voivodeships"] = "invalid"
    elif len(voivs) > share.MAX_COMPARE:
        errors["voivodeships"] = "too_many"
    if errors:
        raise invalid(**errors)
    return respond({"query": share.encode(purpose.value, voivs)})
