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
    master = fileplan.payload()["tree"][0]          # 01000_File-Plan-and-Governance
    fake = FakeTree()
    out = sitemap.seed(fake, master)

    assert out["made"] == len(fake.made)
    assert fake.made[0] == master["n"]
    assert master["n"] + "/01000-09_Templates-Library/01000-09-02_Forms-Master" in fake.made


def test_a_parent_is_always_made_before_its_children():
    """Graph cannot create a folder inside one that is not there yet, so the
    walk order is not a detail."""
    import fileplan
    fake = FakeTree()
    sitemap.seed(fake, fileplan.payload()["tree"][2])   # 03000_Corporate-and-Legal
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
    hr = "08000_Human-Resources_RESTRICTED"
    assert sitemap.plan_master("8000")["n"] == hr
    assert sitemap.plan_master("08000")["n"] == hr
    assert sitemap.plan_master(hr)["n"] == hr


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


def test_the_pages_upload_limit_matches_the_servers():
    """The page warns before sending anything over the limit. If the two
    numbers drift, it either blocks files the server would take or lets
    people wait on uploads the server is about to refuse."""
    import re
    with open(os.path.join(HERE, "site", "fileplan.html"), encoding="utf-8") as f:
        m = re.search(r"var MAX_UPLOAD_MB\s*=\s*(\d+)\s*;", f.read())
    assert m, "fileplan.html no longer declares MAX_UPLOAD_MB"
    assert int(m.group(1)) * 1024 * 1024 == sitemap.MAX_UPLOAD


# ---------------------------------------------------------------------------
#  Templates: new folders copied from a _TEMPLATE_ next to them
# ---------------------------------------------------------------------------

class GraphFake(sitemap.Tree):
    """A Tree whose SharePoint is a set of paths. Records every write."""

    def __init__(self, paths):
        super().__init__(tenant="t", client_id="c", client_secret="s", host="h",
                         site_path="s", library="l", root="Site Mapping",
                         drive_id="D")
        self.paths = set(paths)
        self.calls = []

    def _kids(self, rel):
        rel = rel.strip("/")
        pre = rel + "/" if rel else ""
        return sorted(p for p in self.paths
                      if p.startswith(pre) and "/" not in p[len(pre):] and p != rel)

    def exists(self, rel):
        return rel.strip("/") in self.paths

    def item(self, rel):
        rel = rel.strip("/")
        if rel not in self.paths:
            raise sitemap.MapError("not there")
        name = rel.split("/")[-1]
        return {"id": "id:" + rel, "name": name, "folder": True,
                "children": len(self._kids(rel)),
                "template": sitemap.is_template(name)}

    def listing(self, rel=""):
        return {"items": [{"name": p.split("/")[-1],
                           "folder": not p.endswith(".pdf"),
                           "children": len(self._kids(p)),
                           "template": sitemap.is_template(p.split("/")[-1])}
                          for p in self._kids(rel)]}

    def rename(self, rel, name):
        rel = rel.strip("/")
        self.calls.append(("rename", rel, name))
        new = sitemap._join(rel.rsplit("/", 1)[0] if "/" in rel else "", name)
        self.paths = {new + p[len(rel):] if p == rel or p.startswith(rel + "/")
                      else p for p in self.paths}

    def create_folder(self, parent, name):
        self.calls.append(("create", parent, name))
        self.paths.add(sitemap._join(parent, name))
        return {"name": name}

    def copy_folder(self, src, parent, name, wait=0, poll=0):
        self.calls.append(("copy", src, parent, name))
        return {"name": name, "done": True}

    def move(self, rel, parent):
        self.calls.append(("move", rel, parent))


HR = "60_HR/60-01_Employee-Files-Active"


def test_a_new_folder_next_to_a_template_is_a_copy_of_it():
    g = GraphFake({"60_HR", HR, HR + "/_TEMPLATE_", HR + "/_TEMPLATE_/A_Application",
                   HR + "/_TEMPLATE_/Medical"})
    out = g.make_record(HR, "SMITH-J_Hire-2026-09-30")
    assert out["template"] is True and out["inside"] == 2
    assert g.calls == [("copy", HR + "/_TEMPLATE_", HR, "SMITH-J_Hire-2026-09-30")]


def test_no_template_means_an_ordinary_empty_folder():
    g = GraphFake({"60_HR", HR})
    out = g.make_record(HR, "Anything")
    assert out["template"] is False
    assert g.calls == [("create", HR, "Anything")]


def test_the_template_can_be_declined_for_one_folder():
    g = GraphFake({"60_HR", HR, HR + "/_TEMPLATE_"})
    g.make_record(HR, "Odd One Out", use_template=False)
    assert g.calls == [("create", HR, "Odd One Out")]


def test_a_template_is_never_made_by_copying_itself():
    g = GraphFake({"60_HR", HR, HR + "/_TEMPLATE_"})
    g.make_record(HR, "_template_")
    assert not any(c[0] == "copy" for c in g.calls)


def test_the_template_name_is_recognised_whatever_the_case():
    assert sitemap.is_template("_TEMPLATE_")
    assert sitemap.is_template("_template_")
    assert not sitemap.is_template("TEMPLATE")
    assert not sitemap.is_template("Template for drivers")


def test_adopting_moves_the_folders_already_there_and_no_files():
    """HR's exact case: the letters and their own additions are the shape of
    one employee, sitting where the employees should go."""
    g = GraphFake({"60_HR", HR, HR + "/A_Application-Resume", HR + "/Medical",
                   HR + "/Time Off Requests", HR + "/stray note.pdf"})
    out = g.make_template(HR, adopt=True)
    assert ("create", HR, "_TEMPLATE_") in g.calls
    moved = sorted(c[1].split("/")[-1] for c in g.calls if c[0] == "move")
    assert moved == ["A_Application-Resume", "Medical", "Time Off Requests"]
    assert all(c[2] == HR + "/_TEMPLATE_" for c in g.calls if c[0] == "move")
    assert sorted(out["moved"]) == moved


def test_without_adopting_nothing_moves():
    g = GraphFake({"60_HR", HR, HR + "/A_Application-Resume"})
    g.make_template(HR, adopt=False)
    assert not any(c[0] == "move" for c in g.calls)


def test_a_second_template_is_refused():
    g = GraphFake({"60_HR", HR, HR + "/_TEMPLATE_"})
    with pytest.raises(sitemap.MapError):
        g.make_template(HR)


def test_the_top_folder_does_not_get_a_template():
    g = GraphFake({"60_HR"})
    with pytest.raises(sitemap.MapError):
        g.make_template("")


@pytest.mark.parametrize("bad", ESCAPES)
def test_templates_stay_inside_the_fence(bad):
    g = GraphFake(set())
    with pytest.raises(sitemap.OutsideRoot):
        g.make_record(bad, "x")
    with pytest.raises(sitemap.OutsideRoot):
        g.make_template(bad)


def test_the_template_is_listed_first(tree):
    tree._json = lambda url: {"value": [
        {"name": "B_Offer", "folder": {"childCount": 0}},
        {"name": "_TEMPLATE_", "folder": {"childCount": 6}},
        {"name": "A_Application", "folder": {"childCount": 0}},
        {"name": "a.pdf", "size": 1}]}
    items = tree.listing("x")["items"]
    assert [i["name"] for i in items] == ["_TEMPLATE_", "A_Application",
                                          "B_Offer", "a.pdf"]
    assert items[0]["template"] is True and items[1]["template"] is False


def test_seeding_puts_a_record_parents_letters_inside_its_template():
    hr = sitemap.plan_master("8000")
    fake = FakeTree()
    sitemap.seed(fake, hr)
    base = "08000_Human-Resources_RESTRICTED/08000-01_Employee-Files-Active"
    kid = "08000-01-01_Application-Resume-and-Onboarding"
    assert base + "/_TEMPLATE_" in fake.made
    assert base + "/_TEMPLATE_/" + kid in fake.made
    assert base + "/" + kid not in fake.made
    # and a folder that is not a record template is untouched
    assert ("08000_Human-Resources_RESTRICTED/08000-03_I9-Files_SEGREGATED/"
            "08000-03-01_Active-Employees") in fake.made


def test_the_copy_asks_graph_for_the_right_thing(tree):
    sent = {}
    tree.exists = lambda rel: False
    tree._json = lambda url: {"id": "ID(" + url.split("root:/")[-1] + ")"}

    def fake_send(method, path, payload=None, headers_out=None, **kw):
        sent.update(method=method, path=path, payload=payload)
        headers_out["location"] = "https://monitor"
        return {}
    tree._send = fake_send
    tree._wait_copy = lambda monitor, wait, poll: monitor == "https://monitor"

    out = tree.copy_folder(HR + "/_TEMPLATE_", HR, "SMITH-J")
    assert out == {"name": "SMITH-J", "done": True}
    assert sent["method"] == "POST"
    assert "/copy?" in sent["path"] and "_TEMPLATE_" in sent["path"]
    assert sent["payload"]["name"] == "SMITH-J"
    assert sent["payload"]["parentReference"]["driveId"] == "DRIVE"
    assert sent["payload"]["parentReference"]["id"].endswith("Employee-Files-Active)")


def test_a_copy_onto_an_existing_name_is_refused_before_graph_is_asked(tree):
    tree.exists = lambda rel: True
    with pytest.raises(sitemap.MapError):
        tree.copy_folder(HR + "/_TEMPLATE_", HR, "SMITH-J")


class _Resp:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return self.body


@pytest.mark.parametrize("answers,expect", [
    ([b'{"status":"inProgress"}', b'{"status":"completed"}'], True),
    (["redirect"], True),                     # older Graph: 303 to the new item
    ([], False),                              # never finishes: gives up
])
def test_waiting_on_a_copy(tree, monkeypatch, answers, expect):
    import orientation
    seq = iter(answers)

    class Opener:
        def open(self, req, timeout=None):
            assert req.get_header("Authorization") is None, \
                "the monitor is pre-authenticated; a token must not be sent"
            a = next(seq, b'{"status":"inProgress"}')
            if a == "redirect":
                raise orientation._Redirected("https://new-item")
            return _Resp(a)
    monkeypatch.setattr(orientation, "_OPENER", Opener())
    monkeypatch.setattr(sitemap.time, "sleep", lambda s: None)
    assert tree._wait_copy("https://monitor", wait=0.05, poll=0.001) is expect


def test_a_failed_copy_says_so(tree, monkeypatch):
    import orientation

    class Opener:
        def open(self, req, timeout=None):
            return _Resp(b'{"status":"failed","error":{"message":"quota"}}')
    monkeypatch.setattr(orientation, "_OPENER", Opener())
    with pytest.raises(sitemap.MapError) as e:
        tree._wait_copy("https://monitor", wait=5, poll=0)
    assert "quota" in str(e.value)


def test_the_template_route_refuses_an_escape(client):
    assert client.post("/api/map/template",
                       json={"path": "../Safety"}).status_code == 403


# ---------------------------------------------------------------------------
#  Renumbering - the move to the File Class index
# ---------------------------------------------------------------------------

def old_tree(master_num):
    """A master folder's branch as it was built under the old numbering."""
    import fileplan
    former = fileplan.former_names()
    master = sitemap.plan_master(master_num)
    paths = set()

    def walk(node, plan_parent, live_parent):
        plan_rel = sitemap._join(plan_parent, node["n"])
        live = sitemap._join(live_parent, former[plan_rel])
        paths.add(live)
        kids_live = live
        if node.get("tm") and node.get("k"):
            kids_live = live + "/_TEMPLATE_"
            paths.add(kids_live)
        for k in node.get("k") or []:
            walk(k, plan_rel, kids_live)
    walk(master, "", "")
    return master, former, paths


def plan_paths(master):
    out = set()

    def walk(node, parent):
        rel = sitemap._join(parent, node["n"])
        out.add(rel)
        kp = rel + "/_TEMPLATE_" if node.get("tm") and node.get("k") else rel
        if kp != rel:
            out.add(kp)
        for k in node.get("k") or []:
            walk(k, kp)
    walk(master, "")
    return out


def test_renumbering_renames_a_whole_branch_in_place():
    master, former, paths = old_tree("3000")
    g = GraphFake(paths)
    out = sitemap.renumber(g, master, former)
    assert out["missing"] == [] and not out["more"]
    assert g.paths == plan_paths(master)
    assert all(c[0] == "rename" for c in g.calls)     # nothing made or moved
    assert out["renamed"] == len(g.calls) == len(paths)


def test_renumbering_keeps_what_is_inside_and_what_is_not_in_the_plan():
    master, former, paths = old_tree("7000")
    paths |= {"50_INSURANCE-AND-RISK/50-01_Policies-in-Force/policy.pdf",
              "50_INSURANCE-AND-RISK/Somebody's Own Folder"}
    g = GraphFake(paths)
    sitemap.renumber(g, master, former)
    assert ("07000_Insurance-and-Risk/07000-01_Policies-in-Force/policy.pdf"
            in g.paths)
    assert "07000_Insurance-and-Risk/Somebody's Own Folder" in g.paths


def test_renumbering_finds_a_folder_somebody_respelled():
    """Site Mapping really has "00_FILE PLAN AND GOVERNANCE", with spaces."""
    master, former, paths = old_tree("1000")
    paths = {p.replace("00_FILE-PLAN-AND-GOVERNANCE",
                       "00_FILE PLAN AND GOVERNANCE") for p in paths}
    g = GraphFake(paths)
    out = sitemap.renumber(g, master, former)
    assert out["missing"] == []
    assert "01000_File-Plan-and-Governance" in g.paths


def test_renumbering_reaches_inside_records_made_from_a_template():
    master, former, paths = old_tree("8000")
    hr = "60_HUMAN-RESOURCES_RESTRICTED/60-01_Employee-Files-Active"
    paths |= {hr + "/SMITH-J_Hire-2026-09-30",
              hr + "/SMITH-J_Hire-2026-09-30/A_Application-Resume-and-Onboarding",
              hr + "/SMITH-J_Hire-2026-09-30/Medical"}
    g = GraphFake(paths)
    out = sitemap.renumber(g, master, former)
    rec = ("08000_Human-Resources_RESTRICTED/08000-01_Employee-Files-Active/"
           "SMITH-J_Hire-2026-09-30")
    assert rec + "/08000-01-01_Application-Resume-and-Onboarding" in g.paths
    assert rec + "/Medical" in g.paths                # HR's own, kept
    assert out["records"] == 1
    assert out["missing"] == []      # a record missing a folder is not news


def test_renumbering_twice_changes_nothing_the_second_time():
    master, former, paths = old_tree("2000")
    g = GraphFake(paths)
    sitemap.renumber(g, master, former)
    g.calls = []
    again = sitemap.renumber(g, master, former)
    assert g.calls == [] and again["renamed"] == 0
    assert again["right"] == len(paths)


def test_renumbering_out_of_time_says_so_and_finishes_next_time():
    master, former, paths = old_tree("3000")
    g = GraphFake(paths)
    first = sitemap.renumber(g, master, former, budget=-1)
    assert first["more"] is True
    out = sitemap.renumber(g, master, former)
    assert not out["more"] and g.paths == plan_paths(master)


def test_a_plan_folder_that_is_not_there_is_reported_not_made():
    master, former, paths = old_tree("2000")
    gone = [p for p in paths if p.endswith("05-06_Exceptions-Illegible-or-Unidentified")][0]
    g = GraphFake(paths - {gone})
    out = sitemap.renumber(g, master, former)
    assert out["missing"] == ["02000_Scan-Intake-and-Workflow/"
                              "02000-06_Exceptions-Illegible-or-Unidentified"]
    assert not any(c[0] == "create" for c in g.calls)
