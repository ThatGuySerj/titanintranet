"""The filing system plan - the transcription, and the page that serves it.

The document is 742 folders of numbered structure. Nobody proof-reads that by
eye, so the shape is checked here instead: numbering runs consecutively inside
every parent, template letters run A, B, C with no gaps, no name carries a
character SharePoint rejects, and nothing is deeper or longer than the plan
says it may be. A dropped line shows up as a gap in a sequence.

The other half is the page. It is served to somebody who may see it, refused
to somebody who may not, and refused on the server rather than by leaving the
link out of the rail - which is the mistake the whole permissions module was
written to stop making.

    python -m pytest test_fileplan.py -q
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fileplan


# ---------------------------------------------------------------------------
#  The transcription
# ---------------------------------------------------------------------------

def nodes():
    return [n for n in fileplan.walk() if n["depth"] > 0]


def test_the_eighteen_master_folders_are_all_there():
    got = [n["num"] for n in fileplan.tree()["kids"]]
    assert got == ["00", "05", "10", "20", "30", "40", "50", "60", "70", "80",
                   "90", "100", "110", "120", "130", "140", "150", "160"]


def test_numbering_runs_consecutively_inside_every_parent():
    """A dropped line in the transcription is a gap in a sequence."""
    for parent in fileplan.walk():
        seq = [int(k["num"].split("-")[-1]) for k in parent["kids"] if k["num"]]
        if not seq or parent["depth"] == 0:
            continue                       # the master folders' gaps are by design
        assert seq == list(range(seq[0], seq[0] + len(seq))), parent["name"]


def test_template_letters_run_a_b_c_with_no_gaps():
    for parent in fileplan.walk():
        letters = [k["name"][0] for k in parent["kids"] if k["letter"]]
        if not letters:
            continue
        assert letters == [chr(ord("A") + i) for i in range(len(letters))], \
            parent["name"]


def test_a_parent_never_mixes_numbered_and_lettered_children():
    """The two mean different things - one folder, or one folder per record."""
    for parent in fileplan.walk():
        kinds = {bool(k["letter"]) for k in parent["kids"]}
        assert len(kinds) <= 1, parent["name"]


def test_no_name_carries_a_character_sharepoint_rejects():
    bad = set('&/\\:*?"<>|#%')
    for n in nodes():
        assert not (set(n["name"]) & bad), n["name"]
        assert " " not in n["name"], n["name"]


def test_nothing_is_deeper_than_the_plan_allows():
    assert max(n["depth"] for n in nodes()) == 4


def test_every_path_leaves_room_for_a_filename():
    """SharePoint stops at 400 characters for path and filename together, and
    the plan promises to leave most of that for the filename."""
    longest = max(len(n["path"]) for n in nodes())
    assert longest <= 200
    assert 400 - longest >= 200


def test_paths_are_unique():
    paths = [n["path"] for n in nodes()]
    assert len(paths) == len(set(paths))


def test_the_walls_are_inherited_all_the_way_down():
    """Everything under a wall is behind it. A folder that raises its own -
    the segregated ones inside restricted HR - keeps its own name for it,
    because segregated says something narrower than restricted does."""
    for n in nodes():
        if n["wall"]:
            for k in n["kids"]:
                assert k["wall"], k["name"]
                if not k["own"]:
                    assert k["wall"] == n["wall"], k["name"]
        else:
            assert not any(k["wall"] and not k["own"] for k in n["kids"])


def test_the_segregated_folders_are_inside_restricted_hr():
    by_name = {n["name"]: n for n in nodes()}
    for name in ("60-03_I-9-Files_SEGREGATED",
                 "60-04_Confidential-Medical-Files_SEGREGATED"):
        assert by_name[name]["path"].startswith(
            "TITAN-GROUP/60_HUMAN-RESOURCES_RESTRICTED/")


def test_every_explained_wall_is_a_folder_that_exists():
    """A typo in WHY would otherwise be invisible: the explanation simply
    never appears next to anything."""
    names = {n["name"] for n in nodes()}
    for key in fileplan.WHY:
        assert key in names, key


def test_every_wall_in_the_tree_is_explained_or_inside_one_that_is():
    explained = set(fileplan.WHY)
    for n in nodes():
        if n["own"]:
            assert n["name"] in explained, n["name"]


def test_every_record_template_exists_and_has_lettered_children():
    by_name = {n["name"]: n for n in nodes()}
    for key in fileplan.TEMPLATE_OF:
        assert key in by_name, key
        kids = by_name[key]["kids"]
        assert kids and all(k["letter"] for k in kids), key


def test_every_lettered_folder_is_explained_one_way_or_the_other():
    """A lettered folder is either part of a record template - copied per
    driver, per unit, per customer - or one of the enumerated entity and lender
    folders that happen to share the same shape. The page says something
    different about each, so every one of them has to fall into one camp."""
    for n in nodes():
        if not n["letter"]:
            continue
        parent_name = n["path"].split("/")[-2]
        grandparent = n["path"].split("/")[-3]
        assert (parent_name in fileplan.TEMPLATE_OF
                or grandparent in fileplan.REPEATED_UNDER), n["path"]


def test_the_enumerated_folders_are_not_called_templates():
    """Saying a folder per entity is made from a template tells somebody they
    can create one, which is the opposite of what the entity wall is for."""
    for name in fileplan.TEMPLATE_OF:
        assert not name.startswith("10-01-")
        assert not name.startswith("40-02-")


def test_the_counts_are_counted_and_not_quoted():
    s = fileplan.stats()
    assert s["folders"] == len(nodes())
    assert s["masters"] == 18
    assert s["depth"] == 4
    assert s["own_walls"] == len([n for n in nodes() if n["own"]])
    assert s["longest"] == len(s["longest_path"])


# ---------------------------------------------------------------------------
#  The metadata
# ---------------------------------------------------------------------------

def test_owners_and_access_cover_every_master_folder_and_no_others():
    nums = {n["num"] for n in fileplan.tree()["kids"]}
    assert set(fileplan.MASTERS) == nums
    assert set(fileplan.MATRIX) == nums


def test_the_access_matrix_is_one_letter_per_role():
    for num, (letters, _) in fileplan.MATRIX.items():
        cells = letters.split()
        assert len(cells) == len(fileplan.ROLES), num
        assert all(c in "FER-" for c in cells), num


def test_hr_is_the_only_role_with_full_access_to_hr():
    """Worth a test of its own: the whole point of 60 being restricted is that
    the letters in its row say so."""
    row = dict(zip(fileplan.ROLES, fileplan.MATRIX["60"][0].split()))
    assert row["HR"] == "F"
    assert row["Controller"] == "-"
    assert row["Dispatch"] == "-"
    assert row["Safety / DOT"] == "-"


# ---------------------------------------------------------------------------
#  The payload
# ---------------------------------------------------------------------------

def test_the_payload_is_json_and_carries_no_derivable_weight():
    blob = fileplan.as_json()
    data = json.loads(blob)
    assert data["stats"]["folders"] == fileplan.stats()["folders"]

    seen = set()

    def keys(node):
        seen.update(node)
        for k in node.get("k", []):
            keys(k)
    for m in data["tree"]:
        keys(m)

    # names and flags only - the title and the path are rebuilt in the browser
    assert seen <= {"n", "w", "o", "L", "tm", "rp", "why", "k"}
    assert "p" not in seen and "t" not in seen


def test_the_payload_carries_every_folder():
    data = json.loads(fileplan.as_json())

    def count(node):
        return 1 + sum(count(k) for k in node.get("k", []))
    assert sum(count(m) for m in data["tree"]) == fileplan.stats()["folders"]


def test_titles_are_readable_and_lose_the_numbering():
    assert fileplan._title("70-02_Drug-and-Alcohol-Program_RESTRICTED") == \
        "Drug and Alcohol Program"
    assert fileplan._title("A_Formation-and-Charter") == "Formation and Charter"
    assert fileplan._title("160_ARCHIVE-AND-INACTIVE") == "ARCHIVE AND INACTIVE"


def test_the_hyphens_that_are_part_of_a_name_survive():
    """"I 9 Files" would be wrong in a way HR would notice immediately."""
    assert fileplan._title("60-03_I-9-Files_SEGREGATED") == "I-9 Files"
    assert fileplan._title("30-08-02_W-2-and-W-3") == "W-2 and W-3"
    assert fileplan._title("30-01-02_K-1s-Issued-and-Received") == \
        "K-1s Issued and Received"
    assert fileplan._title("60-03-03_E-Verify-Records") == "E-Verify Records"
    assert fileplan._title("70-06-01_Annual-Periodic-Inspections-396-17") == \
        "Annual Periodic Inspections 396-17"
    assert fileplan._title("70-10-01_OSHA-300-301-and-300A-Logs") == \
        "OSHA 300-301 and 300A Logs"


def test_the_browsers_copy_of_title_would_agree_with_pythons():
    """The page rebuilds the title in JavaScript. This is that rule, written
    twice - if the two ever disagree, the page shows something the tests never
    saw."""
    def as_the_browser_does(name):
        body = name.split("_", 1)[1] if "_" in name else name
        body = re.sub(r"_(RESTRICTED|SEGREGATED|PARTITIONED)$", "", body)
        parts = body.split("-")
        out = parts[0]
        for i in range(1, len(parts)):
            prev, nxt = parts[i - 1], parts[i]
            keep = bool(re.search(r"[0-9]$", prev) and re.match(r"^[0-9]", nxt)
                        or re.match(r"^[A-Z]$", prev))
            out += ("-" if keep else " ") + nxt
        return out

    for n in nodes():
        assert as_the_browser_does(n["name"]) == n["title"], n["name"]


# ---------------------------------------------------------------------------
#  The page
# ---------------------------------------------------------------------------

PAGE = os.path.join(HERE, "site", "fileplan.html")


def test_the_page_is_on_disk_with_its_markers():
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    assert "/* TITAN-PLAN-START */" in page
    assert "/* TITAN-PLAN-END */" in page
    assert "var PLAN = null;" in page       # nothing baked in


@pytest.fixture()
def client(monkeypatch):
    import app as appmod
    import intranet_access as ia

    monkeypatch.setattr(appmod, "conn", lambda: object())
    monkeypatch.setattr(ia, "groups_for", lambda c, e: {"dispatch"})
    monkeypatch.setattr(ia, "all_rules", lambda c: CLIENT_RULES["rules"])
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


CLIENT_RULES = {"rules": {}}


def sign_in(client, email="driver@tetransports.com"):
    with client.session_transaction() as s:
        s["office"] = True
        s["email"] = email


def test_signed_out_is_sent_to_the_sign_in_page(client):
    CLIENT_RULES["rules"] = {}
    r = client.get("/fileplan")
    assert r.status_code in (302, 401)
    assert "/login" in r.headers.get("Location", "")


def test_signed_in_gets_the_plan_filled_in(client):
    CLIENT_RULES["rules"] = {}
    sign_in(client)
    r = client.get("/fileplan")
    assert r.status_code == 200
    body = r.get_data(as_text=True)

    assert "var PLAN = null;" not in body
    assert "var PLAN = {" in body
    assert "70-02_Drug-and-Alcohol-Program_RESTRICTED" in body
    assert body.count("/* TITAN-PLAN-END */") == 1
    assert r.headers["Cache-Control"] == "no-store, private"
    assert r.headers["Vary"] == "Cookie"


def test_the_injected_block_is_the_whole_payload(client):
    CLIENT_RULES["rules"] = {}
    sign_in(client)
    body = client.get("/fileplan").get_data(as_text=True)

    start = body.index("var PLAN = ") + len("var PLAN = ")
    end = body.index(";\n/* TITAN-PLAN-END */")
    data = json.loads(body[start:end])
    assert data["stats"]["folders"] == fileplan.stats()["folders"]
    assert len(data["tree"]) == 18


def test_restricting_the_rail_link_shuts_the_page_itself(client):
    """The link disappearing from the rail is not the control - this is. A
    hidden link over an open page is a curtain, and that is the one thing this
    site is not allowed to ship."""
    import app as appmod
    CLIENT_RULES["rules"] = {appmod.PLAN_KEY: {"office"}}
    sign_in(client)                                  # in "dispatch", not "office"
    assert client.get("/fileplan").status_code == 403


def test_somebody_in_the_named_group_still_gets_in(client, monkeypatch):
    import app as appmod
    import intranet_access as ia
    monkeypatch.setattr(ia, "groups_for", lambda c, e: {"office"})
    CLIENT_RULES["rules"] = {appmod.PLAN_KEY: {"office"}}
    sign_in(client)
    assert client.get("/fileplan").status_code == 200


def test_the_rail_link_and_the_gate_use_the_same_key():
    """Two spellings of the same name would look fine and lock nothing."""
    import app as appmod
    import intranet_access as ia

    with open(os.path.join(HERE, "site", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    link = [x for x in cfg["homepage"] if x.get("u") == "/fileplan"]
    assert link, "the rail has no link to the file plan"

    keys = [i["key"] for item in ia.inventory(cfg) for i in item["children"]]
    assert appmod.PLAN_KEY in keys
