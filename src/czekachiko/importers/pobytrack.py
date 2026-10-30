"""Import the pobyt-tracker dataset (t.me/pobytrack), used with its maintainers' permission.

The site is static: its HTML references `/assets/site-<hash>.js`, and that bundle embeds a JS
object literal `{generated:"…",lastPost:N,cases:[…]}`. Each case holds a region, basis,
filing method, milestone dates and a post number, which is its stable id. No personal data.

Imported cases belong to repo.SYSTEM_TG_ID with the client token `pobytrack:<post>`. A post
can report several cases; the second and later ones in dataset order get `pobytrack:<post>/2`
and so on, so none is lost. They
count in stats, forecasts and who-now like anyone's case. A re-import updates changed cases,
deletes posts that are gone upstream and recomputes each affected aggregate key once.

The source is pluggable: fetch_dataset() reads the site bundle today; pass a URL to read a
JSON document of the same shape instead. Nothing below it depends on where the data came from.

Runs only by hand, from the bot container (the API container has no internet access):

    docker compose -p czekachiko exec bot \
        python -m czekachiko.importers.pobytrack [--file PATH | --url URL] [--dry-run]

It prints new/updated/unchanged/deleted counts and skips by reason. A failed fetch, a broken
dataset or a run that would delete many imported cases changes nothing.
"""

import argparse
import asyncio
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from czekachiko.dates import validate_milestones
from czekachiko.db import repo
from czekachiko.domain import Channel, Milestone, Purpose, Voivodeship
from czekachiko.share import normalize

SITE_URL = "https://pobyt-tracker.pages.dev/ru/"
SOURCE = "pobytrack"  # cases.source
TOKEN_PREFIX = f"{SOURCE}:"
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 30.0
USER_AGENT = "czekachiko-importer (+https://t.me/czekachiko_bot)"
# Upstream rarely removes posts. A run that would delete more than this many imported cases
# (or this share of them, if larger) is treated as a broken source and changes nothing.
MAX_DELETIONS = 10
MAX_DELETE_SHARE = 0.1
# Keeps `pobytrack:<post>/<n>` inside the 64-character client token.
MAX_POST = 10**12

M = Milestone
BASES: dict[str, Purpose] = {
    "work": Purpose.praca,
    "jdg": Purpose.jdg,
    "bc": Purpose.blue_card,
    "fam": Purpose.rodzina,
    "study": Purpose.studia,
    "temp": Purpose.inne,
    "res": Purpose.rezydent_ue,
    "perm": Purpose.staly,
    # The permit type is unknown too: its own type, never pooled into the others.
    "other": Purpose.nieznane,
}
# Filing method. Anything else, `unk` included, is unknown unless the dates tell (channel_of).
METHODS: dict[str, Channel] = {
    "personal": Channel.in_person,
    "post": Channel.post,
    "edor": Channel.post,  # e-Doręczenia: same path as post
    "mos2": Channel.mos,
}
FIELDS: dict[str, Milestone] = {
    "submitted": M.filed,
    "call": M.braki,
    "fingerprints": M.fingerprints,
    "decision": M.decision,
    "card": M.card,
}
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DatasetError(Exception):
    """The source could not be read or does not look like the dataset. Nothing was changed."""


# --- parsing the bundle ------------------------------------------------------------------


class _Literal:
    """A JSON-like reader for minified JS object literals.

    Handles unquoted keys, `…`/"…"/'…' strings, `!0`/`!1` booleans, null and numbers such
    as `1e3`. Anything else (template expressions, identifiers, calls) is rejected.
    """

    ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}

    def __init__(self, text: str, pos: int = 0):
        self.text, self.pos = text, pos

    def fail(self, what: str):
        raise DatasetError(f"{what} at offset {self.pos}")

    def skip(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def peek(self) -> str:
        self.skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            self.fail(f"expected {ch!r}")
        self.pos += 1

    def value(self):
        ch = self.peek()
        if ch == "{":
            return self.obj()
        if ch == "[":
            return self.arr()
        if ch in "`\"'":
            return self.string()
        if ch == "!":
            word = self.text[self.pos : self.pos + 2]
            if word not in ("!0", "!1"):
                self.fail("unsupported expression")
            self.pos += 2
            return word == "!0"
        if ch == "-" or ch == "." or ch.isdigit():
            return self.number()
        word = self.ident()
        if word == "null":
            return None
        if word in ("true", "false"):
            return word == "true"
        self.fail(f"unsupported identifier {word!r}")

    def obj(self) -> dict:
        self.expect("{")
        out: dict = {}
        while self.peek() != "}":
            ch = self.peek()
            key = self.string() if ch in "`\"'" else self.ident()
            self.expect(":")
            out[key] = self.value()
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != "}":
                self.fail("expected ',' or '}'")
        self.pos += 1
        return out

    def arr(self) -> list:
        self.expect("[")
        out: list = []
        while self.peek() != "]":
            out.append(self.value())
            if self.peek() == ",":
                self.pos += 1
            elif self.peek() != "]":
                self.fail("expected ',' or ']'")
        self.pos += 1
        return out

    def ident(self) -> str:
        self.skip()
        m = re.compile(r"[A-Za-z_$][\w$]*").match(self.text, self.pos)
        if not m:
            self.fail("expected a key or value")
        self.pos = m.end()
        return m.group()

    def number(self) -> int | float:
        m = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?").match(self.text, self.pos)
        if not m:
            self.fail("bad number")
        self.pos = m.end()
        n = float(m.group())
        return int(n) if n.is_integer() else n  # minifiers write 1000 as 1e3

    def string(self) -> str:
        quote = self.text[self.pos]
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text):
                self.fail("unterminated string")
            ch = self.text[self.pos]
            if ch == quote:
                self.pos += 1
                return "".join(out)
            if quote == "`" and self.text.startswith("${", self.pos):
                self.fail("template expression")
            if ch == "\\":
                nxt = self.text[self.pos + 1 : self.pos + 2]
                if nxt == "u":
                    out.append(chr(int(self.text[self.pos + 2 : self.pos + 6], 16)))
                    self.pos += 6
                    continue
                out.append(self.ESCAPES.get(nxt, nxt))
                self.pos += 2
                continue
            out.append(ch)
            self.pos += 1


def extract_dataset(bundle: str) -> dict:
    """The `{generated:…,lastPost:…,cases:[…]}` literal embedded in the site bundle."""
    match = re.search(r"\{\s*generated\s*:", bundle)
    if match is None:
        raise DatasetError("no dataset literal in the bundle")
    data = _Literal(bundle, match.start()).value()
    return check_dataset(data)


def check_dataset(data) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise DatasetError("dataset has no cases list")
    if not data["cases"]:
        raise DatasetError("dataset is empty")
    return data


# --- sources -----------------------------------------------------------------------------


async def _get(client: httpx.AsyncClient, url: str) -> str:
    async with client.stream("GET", url) as r:
        r.raise_for_status()
        chunks, size = [], 0
        async for chunk in r.aiter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise DatasetError(f"{url} is larger than {MAX_BYTES} bytes")
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8")


async def fetch_site_bundle(client: httpx.AsyncClient, page: str = SITE_URL) -> dict:
    html = await _get(client, page)
    match = re.search(r"""["'(]((?:\.{0,2}/)*assets/site-[\w-]+\.js)""", html)
    if match is None:
        raise DatasetError("no site bundle referenced from the page")
    return extract_dataset(await _get(client, urljoin(page, match.group(1))))


async def fetch_json(client: httpx.AsyncClient, url: str) -> dict:
    try:
        data = json.loads(await _get(client, url))
    except ValueError as e:
        raise DatasetError(f"not JSON: {e}") from None
    return check_dataset(data)


async def fetch_dataset(url: str | None = None, client: httpx.AsyncClient | None = None) -> dict:
    """The dataset from the live site, or from a JSON document of the same shape at `url`.

    Raises DatasetError (or an httpx error) on any failure; never returns partial data.
    """
    own = client is None
    client = client or httpx.AsyncClient(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    try:
        return await (fetch_json(client, url) if url else fetch_site_bundle(client))
    finally:
        if own:
            await client.aclose()


def load_file(path: Path) -> dict:
    """A saved dataset: JSON, or the site bundle (.js) it is embedded in."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            return check_dataset(json.loads(text))
        except ValueError as e:
            raise DatasetError(f"not JSON: {e}") from None
    return extract_dataset(text)


# --- mapping -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    key: str  # the post number, plus "/<n>" for the n-th case of a post
    voivodeship: Voivodeship
    purpose: Purpose
    channel: Channel
    dates: dict[Milestone, date]


def region_of(name) -> Voivodeship | None:
    if not isinstance(name, str):
        return None
    try:
        return Voivodeship(normalize(name.strip()).replace("-", "_"))
    except ValueError:
        return None


def post_of(raw) -> int | None:
    post = raw.get("post") if isinstance(raw, dict) else None
    if isinstance(post, float) and post.is_integer():
        post = int(post)  # 1e3 read by a JSON parser
    return post if type(post) is int and 0 < post < MAX_POST else None


def channel_of(method, dates: dict[Milestone, date]) -> Channel:
    """The stated method; without one, fingerprints on the filing day mean in person (only the
    counter takes them that day), and anything else stays unknown."""
    if isinstance(method, str) and method in METHODS:
        return METHODS[method]
    if M.fingerprints in dates and dates[M.fingerprints] == dates.get(M.filed):
        return Channel.in_person
    return Channel.unknown


def map_case(raw, today: date) -> Row | str:
    """A case as our Row (keyed by its post alone), or the reason it is skipped."""
    if not isinstance(raw, dict):
        return "malformed"
    post = post_of(raw)
    if post is None:
        return "post_invalid"
    basis = raw.get("basis")
    if basis not in BASES:
        return "basis_unknown"
    voiv = region_of(raw.get("region"))
    if voiv is None:
        return "region_unknown"
    dates: dict[Milestone, date] = {}
    for key, milestone in FIELDS.items():
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not _ISO_DAY.match(value):
            return "date_malformed"
        try:
            dates[milestone] = date.fromisoformat(value)
        except ValueError:
            return "date_malformed"
    if codes := validate_milestones(dates, today):
        return f"dates_{codes[0]}"
    return Row(str(post), voiv, BASES[basis], channel_of(raw.get("method"), dates), dates)


def map_cases(cases: list, today: date) -> tuple[dict[str, Row], Counter]:
    """Rows by key, and skip reasons. Ordinals count every case of a post, skipped or not,
    so a case keeps its key when a sibling becomes usable or unusable."""
    rows: dict[str, Row] = {}
    skipped: Counter = Counter()
    seen: Counter = Counter()
    for raw in cases:
        if (post := post_of(raw)) is not None:
            seen[post] += 1
        row = map_case(raw, today)
        if isinstance(row, str):
            skipped[row] += 1
            continue
        if seen[post] > 1:
            row = replace(row, key=f"{post}/{seen[post]}")
        rows[row.key] = row
    return rows, skipped


# --- storing -----------------------------------------------------------------------------


@dataclass
class Report:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    skipped: Counter = field(default_factory=Counter)
    recomputed: int = 0  # aggregate keys (voivodeship + purpose)

    @property
    def changes(self) -> int:
        return self.new + self.updated + self.deleted

    def lines(self) -> list[str]:
        out = [
            f"new: {self.new}",
            f"updated: {self.updated}",
            f"unchanged: {self.unchanged}",
            f"deleted: {self.deleted}",
            f"skipped: {sum(self.skipped.values())}",
        ]
        out += [f"  {reason}: {n}" for reason, n in sorted(self.skipped.items())]
        out.append(f"aggregate keys recomputed: {self.recomputed}")
        return out


def key_of(token: str) -> str | None:
    """The row key of an imported case's client token."""
    rest = token.removeprefix(TOKEN_PREFIX)
    return rest if rest != token and re.fullmatch(r"\d+(/\d+)?", rest) else None


async def import_dataset(
    s: AsyncSession, data: dict, today: date, *, allow_shrink: bool = False
) -> Report:
    """Upsert the dataset into the session's transaction. The caller commits or rolls back.

    Raises DatasetError, before writing anything, when the run would delete more than
    MAX_DELETIONS imported cases and more than MAX_DELETE_SHARE of them (unless
    `allow_shrink`): a broken source must not empty us.
    """
    rows, skipped = map_cases(check_dataset(data)["cases"], today)
    report = Report(skipped=skipped)
    held = {
        key: case
        for case in await repo.list_cases(s, repo.SYSTEM_TG_ID)
        if (key := key_of(case.client_token)) is not None
    }
    gone = [key for key in held if key not in rows]
    limit = max(MAX_DELETIONS, MAX_DELETE_SHARE * len(held))
    if not allow_shrink and len(gone) > limit:
        raise DatasetError(f"would delete {len(gone)} of {len(held)} imported cases")
    await repo.ensure_user(s, repo.SYSTEM_TG_ID)
    touched: set[tuple[str, str]] = set()

    for row_key, row in rows.items():
        case = held.get(row_key)
        key = (row.voivodeship.value, row.purpose.value)
        if case is None:
            token = f"{TOKEN_PREFIX}{row_key}"
            await repo.import_case(
                s, token, row.voivodeship, row.purpose, row.channel, row.dates, SOURCE
            )
            report.new += 1
            touched.add(key)
            continue
        if (case.voivodeship, case.purpose) != key:
            # The calendar event lives in the old voivodeship's calendar: start over.
            touched.add((case.voivodeship, case.purpose))
            await repo.delete_case(s, case, recompute=False)
            await repo.import_case(
                s, case.client_token, row.voivodeship, row.purpose, row.channel, row.dates, SOURCE
            )
            report.updated += 1
            touched.add(key)
            continue
        changed = case.channel != row.channel
        if changed:
            # Statistics are split by channel, so the key is recomputed for this alone.
            case.channel = row.channel
            touched.add(key)
            await repo.enqueue_calendar(s, case)  # events name the channel
        if await repo.write_dates(s, case, row.dates):
            touched.add(key)
            changed = True
        if changed:
            report.updated += 1
        else:
            report.unchanged += 1

    # Gone upstream, or no longer usable (e.g. its basis became "other").
    for row_key, case in held.items():
        if row_key not in rows:
            touched.add((case.voivodeship, case.purpose))
            await repo.delete_case(s, case, recompute=False)
            report.deleted += 1

    await s.flush()
    if touched:
        await repo.recompute_many(s, touched)
    report.recomputed = len(touched)
    return report


async def sync(
    factory: async_sessionmaker,
    data: dict,
    today: date,
    *,
    dry_run: bool = False,
    allow_shrink: bool = False,
) -> Report:
    """One import in one transaction: committed, or rolled back for a dry run.

    Any exception (DatasetError included) leaves the database as it was.
    """
    async with factory() as s:
        report = await import_dataset(s, data, today, allow_shrink=allow_shrink)
        if dry_run:
            await s.rollback()
        else:
            await s.commit()
    return report


# --- command line ------------------------------------------------------------------------


async def _main(args: argparse.Namespace) -> int:
    from czekachiko.config import Settings
    from czekachiko.db.session import make_session_factory

    try:
        data = load_file(Path(args.file)) if args.file else await fetch_dataset(args.url)
    except Exception as e:  # noqa: BLE001 — unreadable file, network, HTTP status, parsing
        print(f"cannot read the dataset, nothing changed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    engine, factory = make_session_factory(Settings().database_url, pool_size=1, max_overflow=0)
    try:
        report = await sync(
            factory, data, date.today(), dry_run=args.dry_run, allow_shrink=args.allow_shrink
        )
    except DatasetError as e:
        print(f"refused, nothing changed: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — the transaction rolled back
        print(f"import failed, nothing changed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(f"generated: {data.get('generated')} · cases in dataset: {len(data['cases'])}")
    print("\n".join(report.lines()))
    if args.dry_run:
        print("dry run: nothing was saved")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m czekachiko.importers.pobytrack")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", help="a saved dataset: .json, or the site bundle (.js)")
    source.add_argument("--url", help="a JSON document of the same shape instead of the site")
    parser.add_argument("--dry-run", action="store_true", help="report, then roll back")
    parser.add_argument(
        "--allow-shrink",
        action="store_true",
        help="accept a run that deletes many imported cases (see MAX_DELETIONS)",
    )
    return asyncio.run(_main(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
