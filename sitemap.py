"""Reading and WRITING one SharePoint folder, for the filing system editor.

The file plan stopped being a drawing. `/fileplan` now browses a real folder in
SharePoint and can change it: new folders, renames, moves, uploads, deletes.
SharePoint is the database; the intranet is the face with the logo on it.

    All Company Documents/
      Site Mapping/          <- MAP_ROOT. Everything here is fair game.
      Safety/                <- everything else is not.
      C Suite/

ONE RULE HOLDS THIS TOGETHER. Every path that arrives from a browser is
resolved against the root and checked to still be inside it afterwards. A
request naming `../Safety` resolves to something outside and is refused before
a single Graph call is made. That check is in `_full()` and it is the only way
in - none of the write methods build a path any other way.

That matters more here than it would elsewhere, because the app registration
holds `Sites.ReadWrite.All`: Microsoft will let it write anywhere in the
tenant. What keeps it inside one folder is this file. So `_full()` gets tests
of its own, and if you add a method that takes a path, it goes through
`_full()` or it does not go in.

When the structure graduates from Site Mapping to the root of the library, one
setting changes - MAP_ROOT to empty - and the guard widens with it. Nothing
else needs touching.

Auth, the token cache and the drive lookup are inherited from
orientation.Library rather than written again, so one Entra app and one drive
resolution serve both features.

Graph endpoints beyond the ones orientation.py already uses:

    POST   /drives/{drive}/items/{parent}/children       make a folder
    PATCH  /drives/{drive}/items/{id}                    rename, move
    DELETE /drives/{drive}/items/{id}                    to the recycle bin
    PUT    /drives/{drive}/items/{parent}:/{name}:/content    upload
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import orientation
from orientation import GRAPH, OrientationError

# The folder everything lives under while the shape is being argued about.
# Empty means the whole library, which is what this becomes if the structure
# is ever promoted out of Site Mapping.
ROOT = (os.environ.get("MAP_ROOT") or "Site Mapping").strip().strip("/")

# Simple uploads only. Graph wants a resumable session above 4 MB and the web
# app is a Basic B1 holding the whole body in memory while it forwards it -
# neither is a fight worth having for a filing structure. Bigger files go
# straight into SharePoint, which is one click away from every folder here.
MAX_UPLOAD = 4 * 1024 * 1024

# A folder with this name inside a parent is the shape every new folder made in
# that parent is copied from - the plan's own rule for record folders, section
# 2.4: "A _TEMPLATE_ folder sits inside each of these parents. Copy it, rename
# it, and every driver file looks like every other driver file." Make a folder
# in 08000-01_Employee-Files-Active called SMITH-J_Hire-2026-09-30 and it arrives
# with every subfolder the template has, and any blank forms in them too.
#
# Everything about it is ordinary SharePoint. The template is a real folder HR
# can open and change; nothing about the copy is stored anywhere else.
TEMPLATE = "_TEMPLATE_"


def is_template(name):
    return (name or "").strip().lower() == TEMPLATE.lower()


def _join(a, b):
    return ("%s/%s" % ((a or "").strip("/"), b)).strip("/")

# SharePoint's own rules, applied before Graph has to say no in its own words.
BAD_CHARS = set('"*:<>?/\\|')
RESERVED = {".lock", "con", "prn", "aux", "nul", "desktop.ini", "_vti_",
            "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8",
            "com9", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7",
            "lpt8", "lpt9"}


class MapError(OrientationError):
    """Something the person at the browser needs told about."""


class OutsideRoot(MapError):
    """A path that resolved to somewhere this is not allowed to touch."""


def clean_name(name):
    """One folder or file name, or an explanation of why it is not one."""
    name = (name or "").strip()
    if not name:
        raise MapError("A name is needed.")
    if len(name) > 255:
        raise MapError("That name is too long - 255 characters at most.")
    bad = sorted(set(name) & BAD_CHARS)
    if bad:
        raise MapError("SharePoint will not accept %s in a name. Use a hyphen "
                       "or an underscore instead." % " ".join(bad))
    if any(ord(c) < 32 for c in name):
        raise MapError("That name has a control character in it.")
    if name in (".", ".."):
        raise MapError("That is not a name.")
    if name.startswith("~") or name.startswith("."):
        raise MapError("A name cannot start with %r - SharePoint hides it."
                       % name[0])
    if name.endswith("."):
        raise MapError("A name cannot end with a full stop.")
    stem = name.split(".")[0].lower()
    if stem in RESERVED or name.lower() in RESERVED:
        raise MapError("%r is a name Windows reserves. Pick another." % name)
    return name


_DIGITS = re.compile(r"(\d+)")


def sort_key(name):
    """Sort a folder list the way the numbering means it, not the way ASCII does.

    The plan's numbers are what put the structure in order, and SharePoint
    sorts them as text. The File Class index pads master folders to five
    digits (01000 ... 18000) so SharePoint gets them right on its own, but
    folders people add by hand are not always padded, and the old numbering
    (100_SALES between 10_CORPORATE and 110_VENDORS) was not. Splitting the
    digits out and comparing them as numbers puts every one of them where it
    belongs. SharePoint still shows what SharePoint shows - this is the
    intranet's own list.
    """
    parts = _DIGITS.split(name or "")
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def _norm(rel):
    """A browser-supplied relative path, cleaned into segments.

    Refuses rather than repairs. A path with `..` in it did not come from the
    page, and the honest answer to it is no - the same stance orientation.py
    takes about file names.
    """
    rel = (rel or "").strip().strip("/")
    if not rel:
        return []
    if "\\" in rel or "\x00" in rel:
        raise OutsideRoot("That is not a path this can open: %r" % rel[:120])
    parts = [p for p in rel.split("/") if p]
    for p in parts:
        if p in (".", ".."):
            raise OutsideRoot("That is not a path this can open: %r" % rel[:120])
    return parts


class Tree(orientation.Library):
    """One folder in a document library, readable and writable.

    Inherits the token, the drive lookup and the error wording from the
    orientation client. `root` here is the Site Mapping folder rather than the
    orientation one, so the same class hierarchy serves both without either
    being able to reach into the other's folder.
    """

    # -- paths -------------------------------------------------------------
    def _full(self, rel=""):
        """The library-relative path, guaranteed to be inside the root.

        THE guard. Every method that takes a path from outside calls this.
        """
        parts = _norm(rel)
        root = [p for p in self.root.split("/") if p]
        full = root + parts
        # Belt and braces: _norm has already refused `..`, and this checks the
        # result rather than the input, so a future change to _norm cannot
        # quietly open a way out.
        if root and full[:len(root)] != root:
            raise OutsideRoot("That path is outside %s." % self.root)
        return "/".join(full)

    def _item_url(self, rel="", suffix=""):
        """The Graph address of one item, or of something hanging off it.

        `suffix` is "/children" or "/content" and carries its own slash. Graph
        addresses a path-named item as `root:/the/path`, and only wants the
        closing colon when something follows it - `root:/the/path:` on its own
        is a 400.
        """
        full = self._full(rel)
        if not full:
            return "/drives/%s/root%s" % (self.drive_id(), suffix)
        base = "/drives/%s/root:/%s" % (self.drive_id(),
                                        urllib.parse.quote(full))
        return base + (":" + suffix if suffix else "")

    # -- talking to Graph --------------------------------------------------
    def _send(self, method, path, payload=None, raw=None, ctype=None,
              headers_out=None):
        """One write to Graph. `headers_out`, if given, collects the response
        headers - a copy answers 202 with nothing in the body and the only
        useful thing it says is in Location."""
        url = path if path.startswith("http") else GRAPH + path
        body = raw
        if payload is not None:
            body = json.dumps(payload).encode()
            ctype = "application/json"
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", "Bearer " + self.token())
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                if headers_out is not None:
                    headers_out.update({k.lower(): v for k, v in r.headers.items()})
                text = r.read()
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 403:
                raise MapError(
                    "Microsoft refused (403). The app registration needs "
                    "Sites.ReadWrite.All with admin consent - read alone is "
                    "enough to browse this folder but not to change it. %s"
                    % detail)
            if e.code == 404:
                raise MapError("That is not there any more. Refresh and try "
                               "again. %s" % detail)
            if e.code == 409:
                raise MapError("Something with that name is already there.")
            if e.code == 423:
                raise MapError("SharePoint has that item locked - somebody has "
                               "it open. Try again in a minute.")
            if e.code == 429:
                raise MapError("SharePoint is asking us to slow down. Wait a "
                               "moment and try again.")
            raise MapError("Graph %s: %s %s" % (url, e.code, detail))

    # -- reading -----------------------------------------------------------
    def listing(self, rel=""):
        """One folder: its own details, and what is directly inside it."""
        select = ("id,name,size,folder,file,webUrl,lastModifiedDateTime,"
                  "lastModifiedBy,createdDateTime")
        url = self._item_url(rel, "/children")
        out = self._json(url + "?$top=200&$select=" + select)
        rows = list(out.get("value", []))
        nxt = out.get("@odata.nextLink")
        pages = 0
        while nxt and pages < 20:
            out = self._json(nxt)
            rows.extend(out.get("value", []))
            nxt = out.get("@odata.nextLink")
            pages += 1

        items = [self._row(r) for r in rows]
        # folders first, and the template first of those - it is what the
        # rest of the folder is made from, so it goes at the top
        items.sort(key=lambda i: (not i["folder"], not i["template"],
                                  sort_key(i["name"])))
        return {"path": rel.strip("/"), "root": self.root, "items": items}

    @staticmethod
    def _row(r):
        folder = r.get("folder") or None
        by = ((r.get("lastModifiedBy") or {}).get("user") or {})
        return {
            "id": r.get("id"),
            "name": r.get("name"),
            "folder": bool(folder),
            "children": (folder or {}).get("childCount", 0) if folder else 0,
            "size": r.get("size") or 0,
            "url": r.get("webUrl"),
            "modified": r.get("lastModifiedDateTime"),
            "by": by.get("displayName") or "",
            "template": bool(folder) and is_template(r.get("name")),
        }

    def item(self, rel):
        """One item's details. Used to check a thing is what the caller thinks."""
        return self._row(self._json(self._item_url(rel)))

    def exists(self, rel):
        try:
            self.item(rel)
            return True
        except OrientationError:
            return False

    # -- writing -----------------------------------------------------------
    def create_folder(self, rel_parent, name):
        """A new folder inside rel_parent.

        conflictBehavior is `fail` and never `replace`: replacing a folder in
        Graph takes the existing one and everything in it with it. Seeding
        wants "leave it alone if it is there", and that is `seed()` checking
        first - not a flag one careless edit away from emptying a folder.
        """
        name = clean_name(name)
        self._full(rel_parent)                   # the guard
        return self._send("POST", self._item_url(rel_parent, "/children"), {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        })

    # -- templates ---------------------------------------------------------
    def template_of(self, rel_parent):
        """The template folder inside rel_parent, or None if it has none."""
        self._full(rel_parent)                   # the guard
        try:
            return self.item(_join(rel_parent, TEMPLATE))
        except OrientationError:
            return None

    def make_record(self, rel_parent, name, use_template=True):
        """A new folder in rel_parent - copied from its template if it has one.

        This is what the New folder button calls. A folder with no template
        gets an ordinary empty folder, exactly as before; a folder with one
        gets a copy of it, subfolders and files and all, under the new name.
        `use_template=False` is the escape hatch for the odd folder that should
        not look like the others.
        """
        name = clean_name(name)
        self._full(rel_parent)                   # the guard
        tmpl = None
        if use_template and not is_template(name):
            tmpl = self.template_of(rel_parent)
        if not tmpl:
            out = self.create_folder(rel_parent, name)
            return {"name": out.get("name") or name, "template": False,
                    "done": True}
        out = self.copy_folder(_join(rel_parent, TEMPLATE), rel_parent, name)
        return {"name": name, "template": True, "done": out["done"],
                "inside": tmpl["children"]}

    def copy_folder(self, rel_src, rel_parent, name, wait=25.0, poll=0.8):
        """Copy a folder and everything in it. Waits up to `wait` seconds.

        Graph copies in the background: it answers 202 at once with a monitor
        address, and the copy finishes in its own time - a second or two for a
        handful of empty folders, longer if the template holds files. This
        waits a while so the ordinary case comes back finished, and says so
        honestly (`done: False`) when it did not.
        """
        name = clean_name(name)
        self._full(rel_src)                      # the guard, on both ends
        self._full(rel_parent)
        if self.exists(_join(rel_parent, name)):
            raise MapError("Something called %r is already there." % name)
        src_id = self._json(self._item_url(rel_src))["id"]
        parent_id = self._json(self._item_url(rel_parent))["id"]
        drive = self.drive_id()
        hdrs = {}
        self._send("POST",
                   "/drives/%s/items/%s/copy?@microsoft.graph.conflictBehavior=fail"
                   % (drive, src_id),
                   {"parentReference": {"driveId": drive, "id": parent_id},
                    "name": name},
                   headers_out=hdrs)
        return {"name": name,
                "done": self._wait_copy(hdrs.get("location"), wait, poll)}

    def _wait_copy(self, monitor, wait, poll):
        """Poll a copy's monitor until it finishes or `wait` runs out.

        The monitor address is pre-authenticated, so it is asked WITHOUT the
        bearer token - and through the opener that does not follow redirects,
        because some Graph versions answer a finished copy with a 303 to the
        new folder, and following that without a token is a 401.
        """
        if not monitor:
            return False
        deadline = time.time() + wait
        while True:
            try:
                req = urllib.request.Request(monitor)
                with orientation._OPENER.open(req, timeout=30) as r:
                    st = json.loads(r.read() or b"{}")
            except orientation._Redirected:
                return True
            except (urllib.error.URLError, ValueError):
                return False
            status = (st.get("status") or "").lower()
            if status == "completed":
                return True
            if status == "failed":
                why = (st.get("error") or {}).get("message") or "no reason given"
                raise MapError("SharePoint could not copy the template: %s" % why)
            if time.time() + poll > deadline:
                return False
            time.sleep(poll)

    def make_template(self, rel, adopt=False):
        """Give a folder a template.

        `adopt` moves the subfolders already there into it. That is the case
        HR is in with 08000-01_Employee-Files-Active: the template folders and the
        ones added since are the shape of ONE employee's file, sitting where
        the employees themselves should go. Only folders move - a loose file in
        the parent would otherwise turn up in every new employee's folder.
        """
        self._full(rel)                          # the guard
        if not _norm(rel):
            raise MapError("The top folder holds the plan's master folders, not "
                           "records - it does not get a template.")
        if self.template_of(rel):
            raise MapError("This folder already has a template.")
        self.create_folder(rel, TEMPLATE)
        moved = []
        if adopt:
            for it in self.listing(rel)["items"]:
                if it["folder"] and not is_template(it["name"]):
                    self.move(_join(rel, it["name"]), _join(rel, TEMPLATE))
                    moved.append(it["name"])
        return {"template": _join(rel, TEMPLATE), "moved": moved}

    def rename(self, rel, name):
        name = clean_name(name)
        self._full(rel)                          # the guard
        if not _norm(rel):
            raise MapError("The top folder is not ours to rename.")
        return self._send("PATCH", self._item_url(rel), {"name": name})

    def move(self, rel, rel_new_parent):
        """Into another folder, keeping the name."""
        self._full(rel)                          # the guard, on both
        parent_full = self._full(rel_new_parent)
        if not _norm(rel):
            raise MapError("The top folder is not ours to move.")

        here = _norm(rel)
        there = _norm(rel_new_parent)
        if there[:len(here)] == here:
            raise MapError("A folder cannot be moved inside itself.")
        if there == here[:-1]:
            raise MapError("It is already there.")

        parent = (self._json(self._item_url(rel_new_parent)) if parent_full
                  else self._json("/drives/%s/root" % self.drive_id()))
        return self._send("PATCH", self._item_url(rel),
                          {"parentReference": {"id": parent["id"]}})

    def delete(self, rel):
        """To the site's recycle bin, where it can be got back for 93 days."""
        self._full(rel)                          # the guard
        if not _norm(rel):
            raise MapError("The top folder is not ours to delete.")
        self._send("DELETE", self._item_url(rel))
        return {"deleted": rel}

    def upload(self, rel_parent, name, data):
        name = clean_name(name)
        if not data:
            raise MapError("That file is empty.")
        if len(data) > MAX_UPLOAD:
            raise MapError(
                "That file is %.1f MB and this takes up to %d MB. Put it "
                "straight into SharePoint - the folder is one click away."
                % (len(data) / 1048576.0, MAX_UPLOAD // 1048576))
        self._full(rel_parent)                   # the guard
        rel = ((rel_parent or "").strip("/") + "/" + name).strip("/")
        return self._send("PUT", self._item_url(rel, "/content"),
                          raw=data, ctype="application/octet-stream")


def from_env():
    """A Tree over MAP_ROOT, using the same app registration as everything else."""
    lib = orientation.from_env()
    return Tree(
        tenant=lib.tenant, client_id=lib.client_id,
        client_secret=lib.client_secret, host=lib.host,
        site_path=lib.site_path, library=lib.library,
        root=ROOT, drive_id=lib._drive_id,
    )


# ---------------------------------------------------------------------------
#  Seeding the plan
# ---------------------------------------------------------------------------

def seed(tree, master, progress=None):
    """Create one master folder's branch of the file plan inside the root.

    One master folder per call on purpose. The whole plan is 732 folders and
    Graph takes one request per folder: done in a single request it would sit
    for minutes and gunicorn would cut it off at 120 seconds with half the
    tree made and no way to tell which half. Eighteen calls of forty-odd
    folders each finish in a few seconds apiece, and the page can show
    progress.

    Re-running is safe. Existing folders are left alone, so a call that failed
    halfway through can simply be made again.
    """
    made, kept = 0, 0

    def ensure(parent_rel, name):
        nonlocal made, kept
        rel = _join(parent_rel, name)
        if tree.exists(rel):
            kept += 1
        else:
            tree.create_folder(parent_rel, name)
            made += 1
            if progress:
                progress(rel)
        return rel

    def walk(node, parent_rel):
        rel = ensure(parent_rel, node["n"])
        # A record-template parent - Employee Files, Driver Qualification
        # Files, Unit Files and the rest - gets its lettered folders inside a
        # _TEMPLATE_, not loose in the parent. They are the shape of one
        # employee's file, and a new employee's folder is copied from them.
        kids_parent = rel
        if node.get("tm") and node.get("k"):
            kids_parent = ensure(rel, TEMPLATE)
        for kid in node.get("k") or []:
            walk(kid, kids_parent)

    walk(master, "")
    return {"made": made, "kept": kept,
            "folders": made + kept, "master": master["n"]}


def plan_master(name):
    """One master folder out of fileplan.py, by name or by File Class.

    "08000_Human-Resources_RESTRICTED", "08000" and "8000" all find HR.
    """
    import fileplan
    want = (name or "").strip().lower()
    for node in fileplan.payload()["tree"]:
        head = node["n"].split("_")[0]
        if want in (node["n"].lower(), head, fileplan._number(node["n"])):
            return node
    raise MapError("There is no master folder called %r in the plan." % name)


# ---------------------------------------------------------------------------
#  Renumbering - the move to the CFO's File Class index
# ---------------------------------------------------------------------------

class _OutOfTime(Exception):
    pass


def _key(name):
    """A name with everything but its letters and digits taken out.

    The old folders were not all spelled the way the plan spelled them: one
    master folder had been renamed to "00_FILE PLAN AND GOVERNANCE", spaces
    and all. Matching on letters and digits alone finds it anyway.
    """
    s = (name or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def renumber(tree, master, former, budget=80.0):
    """Rename one master folder's branch from the old numbering to the index's.

    RENAMES, NEVER RECREATES. The folders already in Site Mapping have files
    in them - Insurance and Safety do - and HR has added folders of its own.
    A rename in SharePoint keeps the folder's contents, its id, its sharing and
    its history. Building the new tree beside the old one and moving things
    across would keep none of that for free.

    `former` maps each plan path (below TITAN-GROUP) to the name the folder had
    before - fileplan.former_names(). A live folder is matched to its old name
    on letters and digits only (see _key), inside the parent it should be in.
    Nothing outside the plan is touched: a folder somebody added keeps its
    name, and so does anything that matches nothing.

    Inside a record template's parent - Employee Files, Driver Qualification
    Files and the rest - the template's folders are renamed, and so are the
    same folders inside every record already made from it, so that SMITH-J's
    file and the next new hire's look the same.

    Safe to run again. A folder that already has its new name is counted and
    left alone, so a run that stops partway - `budget` seconds, because
    gunicorn cuts a request off at 120 - is finished by running it again. The
    answer says `more` when that is needed.
    """
    deadline = time.time() + budget
    out = {"master": master["n"], "renamed": 0, "right": 0, "records": 0,
           "missing": [], "more": False}

    def folders(rel, row=None):
        if row is not None and not row.get("children"):
            return []
        if time.time() > deadline:
            raise _OutOfTime()
        return [it for it in tree.listing(rel)["items"] if it["folder"]]

    def place(parent_rel, live, node, plan_rel, count_missing=True):
        """The live row for this plan folder, renamed if it needed it."""
        want = node["n"]
        for it in live:
            if it["name"] == want:
                out["right"] += 1
                return it
        old = former.get(plan_rel)
        if old:
            hits = [it for it in live if _key(it["name"]) == _key(old)
                    or _key(it["name"]) == _key(want)]
            if len(hits) == 1:
                if time.time() > deadline:
                    raise _OutOfTime()
                tree.rename(_join(parent_rel, hits[0]["name"]), want)
                hits[0]["name"] = want
                out["renamed"] += 1
                return hits[0]
        if count_missing:
            out["missing"].append(plan_rel)
        return None

    def walk(node, parent_rel, plan_parent, live):
        plan_rel = _join(plan_parent, node["n"])
        row = place(parent_rel, live, node, plan_rel)
        if row is None or not node.get("k"):
            return
        rel = _join(parent_rel, row["name"])
        here = folders(rel, row)

        if node.get("tm"):
            tmpl = [it for it in here if it["template"]]
            if tmpl:
                trel = _join(rel, tmpl[0]["name"])
                tlive = folders(trel, tmpl[0])
                for kid in node["k"]:
                    walk(kid, trel, plan_rel, tlive)
                for rec in here:
                    if rec["template"]:
                        continue
                    rrel = _join(rel, rec["name"])
                    rlive = folders(rrel, rec)
                    for kid in node["k"]:
                        place(rrel, rlive, kid, _join(plan_rel, kid["n"]),
                              count_missing=False)
                    out["records"] += 1
                return

        for kid in node["k"]:
            walk(kid, rel, plan_rel, here)

    try:
        walk(master, "", "", folders(""))
    except _OutOfTime:
        out["more"] = True
    return out
