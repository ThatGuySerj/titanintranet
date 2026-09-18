"""The proposed front page.

Most of this page is placeholder words, and placeholder words do not need
tests. One thing about it does: it is built from the signed-in person's own
FILTERED config, and the whole point of the permissions work was that a page
cannot show somebody a document the intranet would hide. A mockup that leaked
the restricted names would be leaking them for real.

    python -m pytest test_welcome.py -q
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import welcome


@pytest.fixture(scope="module")
def cfg():
    with open(os.path.join(HERE, "site", "config.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
#  What it makes out of the config
# ---------------------------------------------------------------------------

def test_every_department_gets_a_link_to_its_own_folder(cfg):
    out = welcome.departments(cfg)
    assert out, "no departments came through"
    for d in out:
        assert d["name"]
        assert d["url"].startswith("https://"), d["name"]
        assert "%20" in d["url"] or " " not in d["url"]


def test_the_folder_url_is_the_sharepoint_site_plus_the_base(cfg):
    url = welcome.folder_url(cfg, "All Company Documents/Safety")
    assert url == (cfg["sharepoint"]["site"] +
                   "/All%20Company%20Documents/Safety")


def test_a_department_with_no_folder_gets_no_link():
    assert welcome.folder_url({"sharepoint": {"site": "https://x"}}, "") == ""
    assert welcome.folder_url({}, "All Company Documents/Safety") == ""


def test_the_document_counts_are_the_real_ones(cfg):
    out = {d["name"]: d["docs"] for d in welcome.departments(cfg)}
    for dept in cfg["departments"]:
        assert out[dept["name"]] == len(dept.get("docs") or [])


# ---------------------------------------------------------------------------
#  The part that matters: it only ever shows what it was given
# ---------------------------------------------------------------------------

def test_a_hidden_department_is_not_on_the_page(cfg):
    """The route hands in an already-filtered config. Nothing in here may go
    back to the unfiltered one to fill a gap."""
    import copy
    trimmed = copy.deepcopy(cfg)
    hidden = trimmed["departments"].pop(0)

    data = welcome.payload(trimmed)
    blob = json.dumps(data)

    assert hidden["name"] not in blob

    # Only the names that belong to this department alone. A form called the
    # same thing in two departments is still visible through the other one,
    # and failing on that would be the test being wrong rather than the code.
    elsewhere = set()
    for d in trimmed["departments"]:
        for doc in d.get("docs") or []:
            elsewhere.add(doc["n"])
    for doc in hidden["docs"]:
        if doc["n"] not in elsewhere:
            assert doc["n"] not in blob, doc["n"]


def test_the_sample_lists_only_hold_documents_the_person_can_see(cfg):
    import copy
    trimmed = copy.deepcopy(cfg)
    trimmed["departments"] = trimmed["departments"][:2]

    allowed = set()
    for d in trimmed["departments"]:
        for doc in d.get("docs") or []:
            allowed.add(doc["n"])

    secs = welcome.sections(trimmed)
    for key in ("static", "most", "recent", "favourites"):
        for item in secs[key]["items"]:
            assert item["n"] in allowed, (key, item["n"])


def test_a_person_who_can_see_nothing_gets_an_empty_page_not_a_crash():
    data = welcome.payload({})
    assert data["departments"] == []
    for key in ("static", "most", "recent", "favourites"):
        assert data["sections"][key]["items"] == []


# ---------------------------------------------------------------------------
#  The invented numbers are labelled as invented
# ---------------------------------------------------------------------------

def test_the_counted_lists_are_marked_as_samples(cfg):
    secs = welcome.sections(cfg)
    assert secs["most"]["sample"] is True
    assert secs["recent"]["sample"] is True
    assert secs["favourites"]["sample"] is True
    assert secs["static"]["sample"] is False


def test_the_same_person_sees_the_same_lists_twice(cfg):
    """Deterministic slices rather than random ones - a mockup you cannot
    point at twice is not much use in a meeting."""
    assert welcome.sections(cfg) == welcome.sections(cfg)


# ---------------------------------------------------------------------------
#  The words
# ---------------------------------------------------------------------------

def test_config_overrides_the_defaults_without_losing_the_rest():
    data = welcome.payload({"welcome": {"owner": {"body": "Mine."}}})
    assert data["welcome"]["owner"]["body"] == "Mine."
    assert data["welcome"]["owner"]["name"] == \
        welcome.DEFAULTS["owner"]["name"]
    assert data["welcome"]["safety"]["heading"] == \
        welcome.DEFAULTS["safety"]["heading"]


def test_the_defaults_are_never_mutated_by_an_override():
    before = json.dumps(welcome.DEFAULTS, sort_keys=True)
    welcome.payload({"welcome": {"owner": {"name": "Somebody Else"}}})
    assert json.dumps(welcome.DEFAULTS, sort_keys=True) == before


@pytest.mark.parametrize("email,expected", [
    ("serj.wahl@tetransports.com", "Serj"),
    ("lonnie.ridenbaugh@tetransports.com", "Lonnie"),
    ("swahl@tetransports.com", ""),          # not a name, so no name is used
    ("", ""),
    ("a.b@x.com", ""),                       # one letter is not a first name
])
def test_the_greeting_only_uses_something_that_looks_like_a_name(email, expected):
    assert welcome.first_name(email, "") == expected


def test_it_can_be_turned_off_without_a_deploy(monkeypatch):
    monkeypatch.setenv("WELCOME_PAGE", "0")
    assert welcome.enabled() is False
    monkeypatch.setenv("WELCOME_PAGE", "1")
    assert welcome.enabled() is True
    monkeypatch.delenv("WELCOME_PAGE")
    assert welcome.enabled() is True


# ---------------------------------------------------------------------------
#  The page and the route
# ---------------------------------------------------------------------------

def test_the_page_is_on_disk_with_its_markers():
    with open(os.path.join(HERE, "site", "welcome.html"), encoding="utf-8") as f:
        page = f.read()
    assert "/* TITAN-WELCOME-START */" in page
    assert "/* TITAN-WELCOME-END */" in page
    assert "var HELLO = null;" in page


def test_the_rail_links_to_it():
    with open(os.path.join(HERE, "site", "config.json"), encoding="utf-8") as f:
        conf = json.load(f)
    assert any(x.get("u") == "/welcome" for x in conf["homepage"]), \
        "nothing in the rail points at the mockup"


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("flask")
    pytest.importorskip("psycopg")
    import app as appmod
    import intranet_access as ia
    monkeypatch.setattr(appmod, "conn", lambda: object())
    monkeypatch.setattr(ia, "groups_for", lambda c, e: set())
    monkeypatch.setattr(ia, "all_rules", lambda c: {})
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_signed_out_is_sent_to_sign_in(client):
    r = client.get("/welcome")
    assert r.status_code in (302, 401)


def test_signed_in_gets_the_page_filled_in(client):
    with client.session_transaction() as s:
        s["office"] = True
        s["email"] = "serj.wahl@tetransports.com"
    r = client.get("/welcome")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    assert "var HELLO = null;" not in body
    assert "var HELLO = {" in body
    assert r.headers["Cache-Control"] == "no-store, private"
    assert r.headers["Vary"] == "Cookie"

    start = body.index("var HELLO = ") + len("var HELLO = ")
    data = json.loads(body[start:body.index(";\n/* TITAN-WELCOME-END */")])
    assert data["viewer"]["name"] == "Serj"
    assert data["departments"]


def test_a_restricted_department_never_reaches_the_page(client, monkeypatch):
    """End to end: restrict a card on the Access screen and it is gone from
    the mockup's HTML, not merely hidden in it."""
    import intranet_access as ia
    with open(os.path.join(HERE, "site", "config.json"), encoding="utf-8") as f:
        conf = json.load(f)
    dept = conf["departments"][0]

    monkeypatch.setattr(ia, "all_rules",
                        lambda c: {"dept:" + dept["id"]: {"nobody"}})
    with client.session_transaction() as s:
        s["office"] = True
        s["email"] = "driver@tetransports.com"

    body = client.get("/welcome").get_data(as_text=True)
    assert dept["name"] not in body
    for doc in dept["docs"][:5]:
        assert doc["n"] not in body
