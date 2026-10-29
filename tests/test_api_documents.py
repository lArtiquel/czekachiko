"""The owner's checklist over the API: standard items, own documents, limits, ownership."""

from tests.test_api_cases import OTHER, create


async def docs_of(detail) -> dict:
    return {d["code"] or d["name"]: d for d in detail["documents"]}


async def test_tick_untick_standard_item(api):
    case = await create(api)
    url = f"/api/cases/{case['id']}/documents/std/wniosek"
    detail = await api.json("PUT", url, json={"date": "2026-03-06"})
    assert (await docs_of(detail))["wniosek"]["date"] == "2026-03-06"
    assert (detail["docs_done"], detail["docs_total"]) == (1, 9)
    assert (await api.json("GET", "/api/cases"))[0]["docs_done"] == 1
    detail = await api.json("PUT", url, json={"date": None})
    assert (await docs_of(detail))["wniosek"]["date"] is None
    assert detail["docs_done"] == 0


async def test_standard_code_must_be_on_the_purposes_checklist(api):
    case = await create(api)  # jdg
    for code in ("uczelnia", "zzz", "WNIOSEK"):
        url = f"/api/cases/{case['id']}/documents/std/{code}"
        assert (await api.call("PUT", url, json={"date": "2026-03-06"})).status == 404, code


async def test_document_dates_follow_the_bot_rules(api):
    case = await create(api)  # filed 2026-03-06: earliest allowed is 2026-02-04
    url = f"/api/cases/{case['id']}/documents/std/oplata"
    for body, code in [
        ({"date": "2026-10-30"}, "future"),
        ({"date": "2026-02-03"}, "doc_too_early"),
        ({"date": "yesterday"}, "not_date"),
        ({}, "required"),
    ]:
        got = await api.json("PUT", url, status=422, json=body)
        assert got == {"error": "invalid", "fields": {"date": code}}, body
    await api.json("PUT", url, json={"date": "2026-02-04"})


async def test_own_documents_add_rename_redate_delete(api):
    case = await create(api)
    base = f"/api/cases/{case['id']}/documents"
    detail = await api.json(
        "POST", base, status=201, json={"name": "  Zaświadczenie\n o niekaralności ", "date": None}
    )
    own = detail["documents"][-1]
    assert own["custom"] is True and own["code"] is None and isinstance(own["id"], int)
    assert own["name"] == "Zaświadczenie o niekaralności" and own["date"] is None
    assert detail["docs_total"] == 10

    url = f"{base}/{own['id']}"
    detail = await api.json("PATCH", url, json={"name": "<b>KRK</b>", "date": "2026-03-10"})
    assert detail["documents"][-1] == {**own, "name": "<b>KRK</b>", "date": "2026-03-10"}
    detail = await api.json("PATCH", url, json={"date": None})
    assert (
        detail["documents"][-1]["date"] is None and detail["documents"][-1]["name"] == "<b>KRK</b>"
    )

    detail = await api.json("DELETE", url)
    assert len(detail["documents"]) == 9
    assert (await api.call("DELETE", url)).status == 404


async def test_own_document_validation(api):
    case = await create(api)
    base = f"/api/cases/{case['id']}/documents"
    for body, fields in [
        ({"name": "   ", "date": None}, {"name": "doc_name_empty"}),
        ({"name": "x" * 61}, {"name": "doc_name_long"}),
        ({"name": 5}, {"name": "invalid"}),
        ({"name": "ok", "date": "2026-10-30"}, {"date": "future"}),
        ({"date": "2026-03-06"}, {"name": "invalid"}),
    ]:
        got = await api.json("POST", base, status=422, json=body)
        assert got == {"error": "invalid", "fields": fields}, body
    doc_id = (await api.json("POST", base, status=201, json={"name": "ok"}))["documents"][-1]["id"]
    got = await api.json("PATCH", f"{base}/{doc_id}", status=422, json={"name": "", "date": "x"})
    assert got == {"error": "invalid", "fields": {"name": "doc_name_empty", "date": "not_date"}}


async def test_own_document_limit_is_409(api):
    case = await create(api)
    base = f"/api/cases/{case['id']}/documents"
    for i in range(15):
        await api.json("POST", base, status=201, json={"name": f"Doc {i}", "date": None})
    assert await api.json("POST", base, status=409, json={"name": "One more"}) == {
        "error": "too_many_docs"
    }


async def test_documents_are_reachable_only_through_their_own_case(api):
    mine = await create(api)
    second = await create(api, client_token="tok-second-1")
    theirs = await create(api, uid=OTHER, client_token="tok-theirs-1")
    doc = (
        await api.json(
            "POST",
            f"/api/cases/{theirs['id']}/documents",
            status=201,
            json={"name": "T"},
            uid=OTHER,
        )
    )["documents"][-1]
    mine_doc = (
        await api.json("POST", f"/api/cases/{mine['id']}/documents", status=201, json={"name": "M"})
    )["documents"][-1]
    for path in (
        f"/api/cases/{theirs['id']}/documents/{doc['id']}",
        f"/api/cases/{mine['id']}/documents/{doc['id']}",
        f"/api/cases/{second['id']}/documents/{mine_doc['id']}",
    ):
        assert (await api.call("PATCH", path, json={"name": "hacked"})).status == 404, path
        assert (await api.call("DELETE", path)).status == 404, path
    detail = await api.json("GET", f"/api/cases/{theirs['id']}", uid=OTHER)
    assert detail["documents"][-1]["name"] == "T"
