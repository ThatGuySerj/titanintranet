"""The filing system editor: the fence, the names, and the routes.

The app registration holds Sites.ReadWrite.All, which means Microsoft will let
this app write anywhere in the tenant - every site, including C Suite and the
signed personnel records in Safety. The only thing keeping it inside the Site
Mapping folder is `sitemap.Tree._full()`.

So that function is what most of this file is about. Not because a path with
`..` in it is likely, but because if one ever worked, the blast radius is the
whole company's documents and nothing in SharePoint would stop it.

    python -m pytest test_sitemap.py -q
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sitemap


@pytest.fixture
def tree():
    """A Tree with the drive id filled in, so nothing calls Graph."""
    return sitemap.Tree(tenant="t", client_id="c", client_secret="s",
                        host="titan.sharepoint.com", site_path="sites/Docs",
                        library="All Company Documents", root="Site Mapping",
                        drive_id="DRIVE")


# ---------------------------------------------------------------------------
#  The fence
# ---------------------------------------------------------------------------

ESCAPES = [
    "../Safety",
    "../../C Suite",
    "a/../../Safety",
    "..",
    "./..",
    "a/./../../x",
    "a\\..\\Safety",
    "Safety\x00",
    "/../Safety",
]


@pytest.mark.parametrize("bad", ESCAPES)
def test_nothing_walks_out_of_the_root(tree, bad):
    with pytest.raises(sitemap.OutsideRoot):
        tree._full(bad)


@pytest.mark.parametrize("bad", ESCAPES)
def test_every_write_refuses_it_too(tree, bad):
    """One test per door, because the fence is only as good as the number of
    methods that actually go through it."""
    with pytest.raises(sitemap.OutsideRoot):
        tree.create_folder(bad, "Anything")
    with pytest.raises(sitemap.OutsideRoot):
        tree.rename(bad, "Anything")
    with pytest.raises(sitemap.OutsideRoot):
        tree.delete(bad)
    with pytest.raises(sitemap.OutsideRoot):
        tree.move(bad, "")
    with pytest.raises(sitemap.OutsideRoot):
        tree.move("x", bad)
    with pytest.raises(sitemap.OutsideRoot):
        tree.upload(bad, "x.pdf", b"%PDF-")
    with pytest.raises(sitemap.OutsideRoot):
        tree.listing(bad)


def test_every_path_method_goes_through_the_guard(tree):
    """A method added later that builds its own path would not be covered by
    the test above, and nobody would notice. This notices: if _full stops
    being called, every one of these raises AttributeError instead."""
    calls = []
    tree._full = lambda rel="": (_ for _ in ()).throw(
        AssertionError("_full was called with %r" % rel)) if calls.append(rel) \
        else None

    for call in (lambda: tree.listing("x"),
                 lambda: tree.create_folder("x", "y"),
                 lambda: tree.rename("x", "y"),
                 lambda: tree.delete("x"),
                 lambda: tree.upload("x", "y.pdf", b"z")):
        calls[:] = []
        try:
            call()
        except Exception:
            pass
        assert calls, "a path method that never consulted the guard"


def test_the_root_itself_is_not_deletable(tree):
    for bad in ("", "/", "   "):
        with pytest.raises(sitemap.MapError):
            tree.delete(bad)
        with pytest.raises(sitemap.MapError):
            tree.rename(bad, "Something")


def test_a_folder_cannot_be_moved_inside_itself(tree):
    with pytest.raises(sitemap.MapError):
        tree.move("10_CORPORATE", "10_CORPORATE/10-01_Entity-Records")
    with pytest.raises(sitemap.MapError):
        tree.move("10_CORPORATE", "10_CORPORATE")


def test_ordinary_paths_resolve_under_the_root(tree):
    assert tree._full("") == "Site Mapping"
    assert tree._full("10_CORPORATE") == "Site Mapping/10_CORPORATE"
    assert tree._full("a/b/c") == "Site Mapping/a/b/c"


def test_an_empty_root_means_the_whole_library(tree):
    """What this becomes when the structure graduates out of Site Mapping."""
    tree.root = ""
    assert tree._full("") == ""
    assert tree._full("Safety") == "Safety"
    with pytest.raises(sitemap.OutsideRoot):
        tree._full("../elsewhere")


def test_the_graph_addresses_are_the_shapes_graph_wants(tree):
    assert tree._item_url("") == "/drives/DRIVE/root:/Site%20Mapping"
    assert tree._item_url("", "/children") == \
        "/drives/DRIVE/root:/Site%20Mapping:/children"
    assert tree._item_url("a b", "/content") == \
        "/drives/DRIVE/root:/Site%20Mapping/a%20b:/content"


def test_the_root_of_the_library_addresses_without_a_colon(tree):
    tree.root = ""
    assert tree._item_url("") == "/drives/DRIVE/root"
    assert tree._item_url("", "/children") == "/drives/DRIVE/root/children"


# ---------------------------------------------------------------------------
#  Names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ['a:b', 'a/b', 'a\\b', 'a*b', 'a?b', 'a"b',
                                 'a<b', 'a>b', 'a|b', '', '   ', '.hidden',
                                 '~temp', 'ends.', 'CON', 'nul', 'a' * 300])
def test_names_sharepoint_would_reject_are_refused_here_first(bad):
    with pytest.raises(sitemap.MapError):
        sitemap.clean_name(bad)


@pytest.mark.parametrize("ok", ["10_CORPORATE-AND-LEGAL", "Insurance Folder",
                                "2026-09-18_TET_INV_EOG_v1.pdf", "A_Charter",
                                "Safety & risk".replace("&", "and")])
def test_the_names_the_plan_uses_are_all_fine(ok):
    assert sitemap.clean_name(ok) == ok


def test_a_name_is_trimmed_not_rejected_for_stray_spaces():
    assert sitemap.clean_name("  Billing  ") == "Billing"


def test_every_folder_name_in_the_plan_would_be_accepted():
    """The seed makes 732 folders out of fileplan.py. If one of those names is
    something SharePoint will not take, the seeding stops halfway through."""
    import fileplan
    for node in fileplan.walk():
        if node["depth"]:
            assert sitemap.clean_name(node["name"]) == node["name"]


# ---------------------------------------------------------------------------
#  Uploads
# ---------------------------------------------------------------------------

def test_an_empty_file_is_refused(tree):
    with pytest.raises(sitemap.MapError):
        tree.upload("", "x.pdf", b"")


def test_a_file_over_the_limit_says_so_in_megabytes(tree):
    with pytest.raises(sitemap.MapError) as e:
        tree.upload("", "big.pdf", b"x" * (sitemap.MAX_UPLOAD + 1))
    assert "MB" in str(e.value)
    assert "SharePoint" in str(e.value)


# ---------------------------------------------------------------------------
#  Seeding
# ---------------------------------------------------------------------------

class FakeTree:
    """Records what would have been created."""

    def __init__(self, already=()):
        self.made = []
        self.already = set(already)

    def exists(self, rel):
        return rel in self.already

    def create_folder(self, parent, name):
        self.made.append((parent + "/" + name).strip("/"))
        self.already.add((parent + "/" + name).strip("/"))
        return {"name": name}


def test_seeding_one_master_makes_its_whole_branch():
    import fileplan
    master = fileplan.payload()["tree"][0]          # 00_FILE-PLAN-AND-GOVERNANCE
    fake = FakeTree()
    out = sitemap.seed(fake, master)

    assert out["made"] == len(fake.made)
    assert fake.made[0] == master["n"]
    assert master["n"] + "/00-09_Templates-Library/00-09-02_Forms-Master" in fake.made


def test_a_parent_is_always_made_before_its_children():
    """Graph cannot create a folder inside one that is not there yet, so the
    walk order is not a detail."""
    import fileplan
    fake = FakeTree()
    sitemap.seed(fake, fileplan.payload()["tree"][2])   # 10_CORPORATE-AND-LEGAL
    seen = set()
    for path in fake.made:
        parent = path.rsplit("/", 1)[0]
        if "/" in path:
            assert parent in seen, path
        seen.add(path)


def test_seeding_twice_changes_nothing_the_second_time():
    import fileplan
    master = fileplan.payload()["tree"][1]
    first = FakeTree()
    sitemap.seed(first, master)
    again = sitemap.seed(first, master)
    assert again["made"] == 0
    assert again["kept"] == first.already.__len__()


def test_seeding_resumes_after_a_failure_halfway():
    import fileplan
    master = fileplan.payload()["tree"][1]
    whole = FakeTree()
    sitemap.seed(whole, master)
    half = list(whole.already)[:len(whole.already) // 2]

    resumed = FakeTree(already=half)
    out = sitemap.seed(resumed, master)
    assert out["kept"] == len(half)
    assert out["folders"] == len(whole.already)


def test_asking_for_a_master_folder_that_is_not_in_the_plan():
    with pytest.raises(sitemap.MapError):
        sitemap.plan_master("70_PAYROLL-SECRETS")


def test_a_master_folder_can_be_asked_for_by_number_or_by_name():
    assert sitemap.plan_master("60")["n"] == "60_HUMAN-RESOURCES_RESTRICTED"
    assert sitemap.plan_master("60_HUMAN-RESOURCES_RESTRICTED")["n"] == \
        "60_HUMAN-RESOURCES_RESTRICTED"


# ---------------------------------------------------------------------------
#  The routes
# ---------------------------------------------------------------------------

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
    c = appmod.app.test_client()
    with c.session_transaction() as s:
        s["office"] = True
        s["email"] = "driver@tetransports.com"
    return c


def test_signed_out_gets_nothing(monkeypatch):
    pytest.importorskip("flask")
    import app as appmod
    appmod.app.config["TESTING"] = True
    out = appmod.app.test_client()
    for url in ("/api/map", "/api/map/log"):
        assert out.get(url).status_code in (302, 401)
    assert out.post("/api/map/delete", json={"path": "x"}).status_code in (302, 401)


@pytest.mark.parametrize("bad", ESCAPES)
def test_the_routes_refuse_an_escape_with_403(client, bad):
    """Before SharePoint is troubled at all - these answer even on a server
    with no Graph credentials, which is what tells you the check ran here."""
    r = client.get("/api/map?path=" + bad)
    assert r.status_code == 403
    r = client.post("/api/map/delete", json={"path": bad})
    assert r.status_code == 403


def test_a_bad_name_is_400_and_says_why(client):
    r = client.post("/api/map/folder", json={"path": "", "name": "a:b"})
    assert r.status_code == 400
    assert ":" in json.loads(r.data)["error"]


def test_an_unconfigured_server_says_so_rather_than_crashing(client):
    """No Graph credentials in the test environment, so a well-formed request
    should come back 501 and not 500."""
    r = client.get("/api/map?path=10_CORPORATE")
    assert r.status_code == 501


def test_the_log_survives_having_no_database(client):
    r = client.get("/api/map/log")
    assert r.status_code == 200
    assert json.loads(r.data)["entries"] == []


def test_the_editor_is_shut_by_the_same_switch_as_the_page(client, monkeypatch):
    """One control on the Access screen, not two. Hiding the filing system
    must not leave the API open to anybody who knows the address."""
    import app as appmod
    import intranet_access as ia
    monkeypatch.setattr(ia, "all_rules", lambda c: {appmod.PLAN_KEY: {"office"}})
    assert client.get("/api/map").status_code == 403
    assert client.post("/api/map/folder",
                       json={"path": "", "name": "x"}).status_code == 403


# ---------------------------------------------------------------------------
#  The order the folders come back in
# ---------------------------------------------------------------------------

def test_the_numbering_sorts_as_numbers_and_not_as_text():
    """SharePoint puts 100 between 10 and 110, because it compares "100" with
    "10_" and '0' sorts before '_'. Every numbered filing system hits this and
    everybody blames the numbering."""
    names = ["100_SALES", "10_CORPORATE", "110_VENDORS", "00_FILE-PLAN",
             "05_SCAN", "160_ARCHIVE", "20_FINANCE", "90_OPERATIONS"]
    assert sorted(names, key=sitemap.sort_key) == [
        "00_FILE-PLAN", "05_SCAN", "10_CORPORATE", "20_FINANCE",
        "90_OPERATIONS", "100_SALES", "110_VENDORS", "160_ARCHIVE"]


def test_the_whole_plan_comes_out_in_plan_order():
    import fileplan
    names = [n["name"] for n in fileplan.tree()["kids"]]
    assert sorted(names, key=sitemap.sort_key) == names


def test_unnumbered_names_still_sort_sensibly():
    names = ["zebra.pdf", "Apple.docx", "mango"]
    assert sorted(names, key=sitemap.sort_key) == ["Apple.docx", "mango",
                                                   "zebra.pdf"]


def test_deeper_numbering_sorts_too():
    names = ["10-10_Late", "10-2_Early", "10-1_First"]
    assert sorted(names, key=sitemap.sort_key) == ["10-1_First", "10-2_Early",
                                                   "10-10_Late"]


def test_folders_come_before_files_whatever_they_are_called():
    tree = sitemap.Tree(tenant="t", client_id="c", client_secret="s",
                        host="h", site_path="s", library="l",
                        root="Site Mapping", drive_id="D")
    rows = [{"name": "a-file.pdf", "size": 1, "webUrl": ""},
            {"name": "z-folder", "folder": {"childCount": 2}, "webUrl": ""}]
    items = [tree._row(r) for r in rows]
    items.sort(key=lambda i: (not i["folder"], sitemap.sort_key(i["name"])))
    assert [i["name"] for i in items] == ["z-folder", "a-file.pdf"]
