"""intranet-permissions-v1 tests.

No database: the rules are a plain dict here, which is what the queries return
anyway. What is under test is the decision - who ends up seeing what - because
that is the part where a mistake is quiet. A card that wrongly disappears gets
reported within the hour; a card that wrongly stays gets reported never.

The config is the real one, read off disk, so the keys in these tests are the
keys the admin screen actually writes.

    python -m pytest test_intranet_access.py -q
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import intranet_access as ia


@pytest.fixture(scope="module")
def cfg():
    with open(os.path.join(HERE, "site", "config.json"), encoding="utf-8") as f:
        return json.load(f)


def names(cards):
    return [c["name"] for c in cards]


def docs_of(cards, card_id):
    for c in cards:
        if c["id"] == card_id:
            return [d["n"] for d in c["docs"]]
    return None


# ---------------------------------------------------------------------------
#  Open by default
# ---------------------------------------------------------------------------

def test_no_rules_means_everybody_sees_everything(cfg):
    out, hidden = ia.filter_config(cfg, {}, set())
    assert len(out["departments"]) == len(cfg["departments"])
    assert len(out["yards"]) == len(cfg["yards"])
    assert hidden == {"cards": 0, "docs": 0, "rail": 0, "libs": 0, "tools": 0}


def test_a_new_starter_with_no_groups_still_gets_the_general_stuff(cfg):
    rules = {"dept:accounting": {"office"}}
    out, _ = ia.filter_config(cfg, rules, set())
    assert "Accounting / Finance" not in names(out["departments"])
    assert "Safety" in names(out["departments"])          # nothing said, so open
    assert len(out["yards"]) == len(cfg["yards"])


def test_filtering_never_mutates_the_shared_config(cfg):
    before = json.dumps(cfg, sort_keys=True)
    ia.filter_config(cfg, {"dept:hr": {"hr"}, "yard:sardis": {"office"}}, set())
    ia.filter_config(cfg, {}, {"hr"})
    assert json.dumps(cfg, sort_keys=True) == before, \
        "the parsed config is held once and handed to every request"


# ---------------------------------------------------------------------------
#  Cards
# ---------------------------------------------------------------------------

def test_a_card_rule_hides_the_card_from_everyone_else(cfg):
    rules = {"dept:hr": {"hr"}}
    out, hidden = ia.filter_config(cfg, rules, {"drivers"})
    assert "Human Resources" not in names(out["departments"])
    assert hidden["cards"] == 1


def test_a_card_rule_lets_the_named_group_through(cfg):
    out, _ = ia.filter_config(cfg, {"dept:hr": {"hr"}}, {"hr"})
    assert "Human Resources" in names(out["departments"])


def test_any_one_of_several_groups_is_enough(cfg):
    rules = {"dept:hr": {"hr", "office"}}
    assert "Human Resources" in names(
        ia.filter_config(cfg, rules, {"office"})[0]["departments"])


def test_yards_restrict_the_same_way(cfg):
    out, _ = ia.filter_config(cfg, {"yard:sardis": {"drivers"}}, set())
    assert "Sardis" not in names(out["yards"])
    assert "Cambridge" in names(out["yards"])


# ---------------------------------------------------------------------------
#  Documents - the case this was actually built for
# ---------------------------------------------------------------------------

def test_the_hr_case_everyone_gets_the_few_they_need(cfg):
    # The ask: "there are a couple of things in the hr one that everyone is
    # going to be needing access to". So leave the CARD open and restrict the
    # rows. Everybody sees the HR card carrying only the general documents.
    hr = [d["n"] for d in
          [c for c in cfg["departments"] if c["id"] == "hr"][0]["docs"]]
    general = {"Employee Handbook", "PTO / Time Off Request",
               "W-4 (IRS, current year)"}
    rules = {ia.doc_key("hr", n): {"hr"} for n in hr if n not in general}

    theirs, _ = ia.filter_config(cfg, rules, set())
    assert "Human Resources" in names(theirs["departments"])
    assert set(docs_of(theirs["departments"], "hr")) == general

    mine, _ = ia.filter_config(cfg, rules, {"hr"})
    assert set(docs_of(mine["departments"], "hr")) == set(hr)


def test_a_card_whose_rows_are_all_hidden_goes_too(cfg):
    # Hiding every row and then leaving a heading that names the category is
    # the worst of both worlds.
    hr = [d["n"] for d in
          [c for c in cfg["departments"] if c["id"] == "hr"][0]["docs"]]
    rules = {ia.doc_key("hr", n): {"hr"} for n in hr}
    out, _ = ia.filter_config(cfg, rules, set())
    assert "Human Resources" not in names(out["departments"])


def test_a_card_rule_beats_an_open_document(cfg):
    # The card is the blunt instrument: if it is shut, nothing inside shows,
    # whatever the rows say.
    rules = {"dept:hr": {"hr"}}
    out, _ = ia.filter_config(cfg, rules, {"drivers"})
    assert "Human Resources" not in names(out["departments"])


def test_yard_documents_restrict_per_yard(cfg):
    rules = {ia.doc_key("sardis", "Daily Run Tickets"): {"office"}}
    out, _ = ia.filter_config(cfg, rules, set())
    sardis = [y for y in out["yards"] if y["id"] == "sardis"][0]
    cambridge = [y for y in out["yards"] if y["id"] == "cambridge"][0]
    assert "Daily Run Tickets" not in [d["n"] for d in sardis["docs"]]
    assert "Daily Run Tickets" in [d["n"] for d in cambridge["docs"]]


# ---------------------------------------------------------------------------
#  The rail, the folder list, the popup
# ---------------------------------------------------------------------------

def test_a_whole_rail_group_can_go(cfg):
    out, hidden = ia.filter_config(cfg, {"rail:driverTools": {"drivers"}}, set())
    assert out["driverTools"] == []
    assert hidden["rail"] == len(cfg["driverTools"])
    assert out["quickLinks"]


def test_one_rail_link_can_go(cfg):
    rules = {"link:quickLinks::Company Documents": {"office"}}
    out, _ = ia.filter_config(cfg, rules, set())
    left = [i["n"] for i in out["quickLinks"]]
    assert "Company Documents" not in left
    assert "Dispatch Board" in left


def test_a_folder_in_the_bottom_list_can_go(cfg):
    out, _ = ia.filter_config(cfg, {"lib:Accounts Payable": {"office"}}, set())
    assert "Accounts Payable" not in [x["name"] for x in out["extraLibraries"]]


def test_the_packet_popup_is_removed_not_left_to_refuse(cfg):
    # Leaving the button and letting the API say no shows somebody a thing
    # they cannot have and then tells them off for trying.
    out, _ = ia.filter_config(cfg, {"tool:orientation": {"hr"}}, set())
    assert "orientation" not in out
    out, _ = ia.filter_config(cfg, {"tool:orientation": {"hr"}}, {"hr"})
    assert "orientation" in out


# ---------------------------------------------------------------------------
#  Admins
# ---------------------------------------------------------------------------

def test_an_admin_sees_everything_regardless(cfg):
    rules = {"dept:hr": {"nobody"}, "yard:sardis": {"nobody"},
             "tool:orientation": {"nobody"}, "rail:driverTools": {"nobody"}}
    out, hidden = ia.filter_config(cfg, rules, set(), admin=True)
    assert len(out["departments"]) == len(cfg["departments"])
    assert "orientation" in out
    assert hidden == {"cards": 0, "docs": 0, "rail": 0, "libs": 0, "tools": 0}


def test_breakglass_and_the_admins_group_both_count(monkeypatch):
    monkeypatch.setattr(ia, "BREAKGLASS", ["swahl@tetransports.com"])
    assert ia.is_admin("swahl@tetransports.com", set())
    assert ia.is_admin("hr@tetransports.com", {"admins"})
    assert not ia.is_admin("hr@tetransports.com", {"office"})
    assert not ia.is_admin("", {"admins"})


# ---------------------------------------------------------------------------
#  Input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,want", [
    ("a@b.com, c@d.com", ["a@b.com", "c@d.com"]),
    ("a@b.com\nc@d.com", ["a@b.com", "c@d.com"]),
    ("  A@B.COM  ", ["a@b.com"]),
    ("a@b.com, a@b.com", ["a@b.com"]),
    ("nonsense, a@b.com", ["a@b.com"]),
    ("", []),
])
def test_pasted_email_lists(raw, want):
    assert ia.emails_from(raw) == want


def test_group_names_are_made_safe():
    class FakeCur:
        def __init__(s): s.sql = []
        def execute(s, q, a=None): s.sql.append((q, a))
        def __enter__(s): return s
        def __exit__(s, *a): return False

    class FakeConn:
        def __init__(s): s.cur = FakeCur()
        def cursor(s): return s.cur
        def commit(s): pass

    c = FakeConn()
    assert ia.add_group(c, "  Yard Managers!! ", "Yard Managers") == "yard-managers"
    with pytest.raises(ValueError):
        ia.add_group(c, "!!!", "x")


def test_the_admins_group_cannot_be_deleted():
    with pytest.raises(ValueError):
        ia.drop_group(None, "admins")


# ---------------------------------------------------------------------------
#  The admin screen's list
# ---------------------------------------------------------------------------

def test_inventory_covers_everything_that_can_be_restricted(cfg):
    inv = ia.inventory(cfg)
    kinds = {i["kind"] for i in inv}
    assert kinds == {"rail", "department", "yard", "tool", "folder"}
    assert len([i for i in inv if i["kind"] == "department"]) == 6
    assert len([i for i in inv if i["kind"] == "yard"]) == 7


def test_every_inventory_key_actually_filters_something(cfg):
    # A key on the screen that filters nothing is a tick box that lies.
    for item in ia.inventory(cfg):
        for key in [item["key"]] + [c["key"] for c in item["children"]]:
            out, hidden = ia.filter_config(cfg, {key: {"nobody"}}, set())
            assert sum(hidden.values()) > 0, "%s hid nothing" % key


def test_document_keys_match_the_pages_bookmark_keys(cfg):
    # The page stores bookmarks as "cardId::name". Same shape on purpose, so
    # the two cannot drift.
    assert ia.doc_key("hr", "Employee Handbook") == "doc:hr::Employee Handbook"
