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
    def _send(self, method, path, payload=None, raw=None, ctype=None):
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
        items.sort(key=lambda i: (not i["folder"], i["name"].lower()))
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

    def walk(node, parent_rel):
        nonlocal made, kept
        rel = (parent_rel + "/" + node["n"]).strip("/")
        if tree.exists(rel):
            kept += 1
        else:
            tree.create_folder(parent_rel, node["n"])
            made += 1
            if progress:
                progress(rel)
        for kid in node.get("k") or []:
            walk(kid, rel)

    walk(master, "")
    return {"made": made, "kept": kept,
            "folders": made + kept, "master": master["n"]}


def plan_master(name):
    """One master folder out of fileplan.py, by name or by number."""
    import fileplan
    want = (name or "").strip().lower()
    for node in fileplan.payload()["tree"]:
        if node["n"].lower() == want or node["n"].split("_")[0] == want:
            return node
    raise MapError("There is no master folder called %r in the plan." % name)
