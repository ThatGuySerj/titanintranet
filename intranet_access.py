"""Who sees what on the intranet.

The page used to carry the whole configuration - 149 document names and every
SharePoint folder path - in its own source. Hiding a card in JavaScript would
have been a curtain rather than a lock: View Source and there is the lot,
including folder names that give things away on their own. One of them is
`IT and Infrastructure/Termed Employee Data Recovered/Yvonne Recovered/`.

So the filtering happens here, before the page is sent, and a person's copy of
the page contains only what that person may see.

SharePoint is still the thing protecting the files themselves. Somebody who
guesses a URL is refused by SharePoint, not by us. What this controls is what
people are shown, and what the shape of the library gives away.

    ---------------------------------------------------------------
    THE RULE
    ---------------------------------------------------------------
    An item with no rows in intranet_rule is visible to EVERYONE.
    An item with rows is visible only to those groups.

    So the default is open, and restricting something is an act. A new
    employee is useful on day one without anybody deciding anything,
    which is what was asked for.

    Cards and documents are restricted separately, and that is the
    point of having both:

      * a rule on a CARD hides the card and everything in it;
      * a rule on a DOCUMENT hides just that row.

    Leave the HR card unrestricted and restrict the sensitive rows
    inside it, and everybody sees the HR card with the handful of
    documents everybody needs, while HR sees all fifteen.

Item keys
---------
    dept:hr                          a department card
    yard:barnesville                 a yard card
    doc:hr::Employee Handbook        one document in a card
    rail:quickLinks                  a whole rail group
    link:quickLinks::Dispatch Board  one rail link
    lib:Accounts Payable             a folder in the bottom list
    tool:orientation                 the packet-printing popup

The key for a document is the same `card::name` shape the page already uses for
bookmarks, so the two never drift apart.
"""
import os
import re

SCHEMA = """
CREATE TABLE IF NOT EXISTS intranet_group (
    name  text PRIMARY KEY,
    label text NOT NULL,
    sort  int  NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS intranet_member (
    email      text NOT NULL,
    group_name text NOT NULL REFERENCES intranet_group(name) ON DELETE CASCADE,
    added_by   text,
    added_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (email, group_name)
);

CREATE TABLE IF NOT EXISTS intranet_rule (
    item_key   text NOT NULL,
    group_name text NOT NULL REFERENCES intranet_group(name) ON DELETE CASCADE,
    PRIMARY KEY (item_key, group_name)
);

CREATE INDEX IF NOT EXISTS intranet_member_email ON intranet_member (email);
CREATE INDEX IF NOT EXISTS intranet_rule_item   ON intranet_rule (item_key);
"""

# Seeded on first boot so the admin screen is not an empty page with no way in.
STARTER_GROUPS = [
    ("everyone", "Everyone", 10),
    ("office",   "Office",   20),
    ("drivers",  "Drivers",  30),
    ("hr",       "HR",       40),
    ("safety",   "Safety",   50),
    ("admins",   "Administrators", 90),
]

ADMIN_GROUP = "admins"

# Break glass, same idea and the same variable as the rest of the Titan sites.
BREAKGLASS = [e.strip().lower()
              for e in (os.environ.get("PORTAL_ADMINS") or "").split(",")
              if e.strip()]


# ---------------------------------------------------------------------------
#  Reading the tables
# ---------------------------------------------------------------------------

def ensure(conn):
    """Create the tables and seed the starter groups. Safe to call often."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
        for name, label, sort in STARTER_GROUPS:
            cur.execute("INSERT INTO intranet_group (name, label, sort) "
                        "VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING",
                        (name, label, sort))
    conn.commit()


def _rows(cur):
    """Rows as plain tuples whether the connection hands back dicts or not."""
    out = []
    for r in cur.fetchall():
        out.append(tuple(r.values()) if isinstance(r, dict) else tuple(r))
    return out


def groups_for(conn, email):
    """Every group this person is in, lower-cased. Never raises.

    Fails CLOSED to "no groups", which with the open-by-default rule means the
    person still sees everything unrestricted and nothing that is restricted.
    A database that is down must not quietly hand out access it cannot verify.
    """
    email = (email or "").strip().lower()
    if not email:
        return set()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT group_name FROM intranet_member WHERE email = %s",
                        (email,))
            return {r[0] for r in _rows(cur)}
    except Exception:
        return set()


def all_groups(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT name, label, sort FROM intranet_group "
                    "ORDER BY sort, name")
        return [{"name": r[0], "label": r[1], "sort": r[2]} for r in _rows(cur)]


def all_members(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT email, group_name FROM intranet_member "
                    "ORDER BY email, group_name")
        out = {}
        for email, g in _rows(cur):
            out.setdefault(email, set()).add(g)
        return out


def all_rules(conn):
    """{item_key: {group, ...}}. An item absent from this is open to everyone."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT item_key, group_name FROM intranet_rule")
            out = {}
            for key, g in _rows(cur):
                out.setdefault(key, set()).add(g)
            return out
    except Exception:
        # No tables yet, or the database is unreachable. Open-by-default with
        # no rules is the same as the intranet behaved before any of this
        # existed, which is the right way to fail for a company noticeboard.
        return {}


def is_admin(email, groups):
    email = (email or "").strip().lower()
    return bool(email) and (email in BREAKGLASS or ADMIN_GROUP in (groups or set()))


# ---------------------------------------------------------------------------
#  Writing
# ---------------------------------------------------------------------------

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(value):
    e = (value or "").strip().lower()
    return e if EMAIL.match(e) else ""


def emails_from(text):
    """A pasted list: commas, newlines or spaces. Duplicates dropped, order kept.

    Takes a paste because that is how access actually gets granted - four new
    drivers start and somebody has four addresses in a message.
    """
    out, seen = [], set()
    for chunk in re.split(r"[,\n;\s]+", text or ""):
        e = clean_email(chunk)
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def set_member_groups(conn, email, groups, by=None):
    email = clean_email(email)
    if not email:
        raise ValueError("That does not look like an email address.")
    groups = [g for g in (groups or []) if g]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM intranet_member WHERE email = %s", (email,))
        for g in groups:
            cur.execute("INSERT INTO intranet_member (email, group_name, added_by) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (email, g, by))
    conn.commit()


def drop_member(conn, email):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM intranet_member WHERE email = %s",
                    (clean_email(email),))
    conn.commit()


def set_rule(conn, item_key, groups):
    """Which groups may see one item. An empty list means everyone."""
    item_key = (item_key or "").strip()
    if not item_key:
        raise ValueError("No item was named.")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM intranet_rule WHERE item_key = %s", (item_key,))
        for g in [g for g in (groups or []) if g]:
            cur.execute("INSERT INTO intranet_rule (item_key, group_name) "
                        "VALUES (%s, %s) ON CONFLICT DO NOTHING", (item_key, g))
    conn.commit()


def add_group(conn, name, label):
    """The short name is optional: the screen says so, so it has to be true.

    Left blank it is made from the label - "Yard Managers" becomes
    "yard-managers" - which is the only reason anybody would leave it blank.
    """
    name = re.sub(r"[^a-z0-9_-]+", "-",
                  ((name or "").strip() or (label or "").strip()).lower()).strip("-")
    if not name:
        raise ValueError("A group needs a name.")
    with conn.cursor() as cur:
        cur.execute("INSERT INTO intranet_group (name, label) VALUES (%s, %s) "
                    "ON CONFLICT (name) DO UPDATE SET label = EXCLUDED.label",
                    (name, (label or name).strip()))
    conn.commit()
    return name


def drop_group(conn, name):
    if name == ADMIN_GROUP:
        raise ValueError("The administrators group cannot be deleted.")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM intranet_group WHERE name = %s", (name,))
    conn.commit()


# ---------------------------------------------------------------------------
#  Filtering the config
# ---------------------------------------------------------------------------

def doc_key(card_id, name):
    return "doc:%s::%s" % (card_id, name)


def _allowed(rules, key, groups, admin):
    """Open unless a rule says otherwise. Admins see everything."""
    if admin:
        return True
    need = rules.get(key)
    if not need:
        return True
    return bool(need & (groups or set()))


def filter_config(cfg, rules, groups, admin=False):
    """A copy of the config holding only what this person may see.

    Returns (config, stats). Nothing is mutated in place: the caller holds one
    parsed copy of the file and hands it to every request, so filtering must
    never touch it.
    """
    groups = set(groups or ())
    hidden = {"cards": 0, "docs": 0, "rail": 0, "libs": 0, "tools": 0}

    def ok(key):
        return _allowed(rules, key, groups, admin)

    out = dict(cfg)

    def keep_docs(card_id, docs):
        kept = []
        for d in docs or []:
            if ok(doc_key(card_id, d.get("n", ""))):
                kept.append(d)
            else:
                hidden["docs"] += 1
        return kept

    # -- departments -------------------------------------------------------
    depts = []
    for d in cfg.get("departments") or []:
        if not ok("dept:" + d.get("id", "")):
            hidden["cards"] += 1
            continue
        d2 = dict(d)
        d2["docs"] = keep_docs(d.get("id", ""), d.get("docs"))
        # A card whose every row is hidden is an empty box with a heading that
        # says what it is. Hiding the rows and then advertising the category is
        # the worst of both, so the card goes too.
        if not d2["docs"]:
            hidden["cards"] += 1
            continue
        depts.append(d2)
    out["departments"] = depts

    # -- yards -------------------------------------------------------------
    shared = cfg.get("yardDocs") or []
    yards = []
    for y in cfg.get("yards") or []:
        if not ok("yard:" + y.get("id", "")):
            hidden["cards"] += 1
            continue
        docs = y.get("docs") or shared
        kept = keep_docs(y.get("id", ""), docs)
        if not kept:
            hidden["cards"] += 1
            continue
        y2 = dict(y)
        # Written onto the yard itself rather than left to the shared list,
        # because two yards can now legitimately show different rows.
        y2["docs"] = kept
        yards.append(y2)
    out["yards"] = yards

    # -- rail groups and their links ---------------------------------------
    for group in ("homepage", "quickLinks", "driverTools"):
        if not ok("rail:" + group):
            hidden["rail"] += len(cfg.get(group) or [])
            out[group] = []
            continue
        kept = []
        for item in cfg.get(group) or []:
            if ok("link:%s::%s" % (group, item.get("n", ""))):
                kept.append(item)
            else:
                hidden["rail"] += 1
        out[group] = kept

    # -- the folder list at the bottom -------------------------------------
    libs = []
    for x in cfg.get("extraLibraries") or []:
        if ok("lib:" + x.get("name", "")):
            libs.append(x)
        else:
            hidden["libs"] += 1
    out["extraLibraries"] = libs

    # -- the packet popup --------------------------------------------------
    # Removed outright rather than left to fail at the API, so somebody who
    # cannot print packets is not shown a button that refuses them.
    if not ok("tool:orientation"):
        if out.pop("orientation", None) is not None:
            hidden["tools"] += 1

    return out, hidden


# ---------------------------------------------------------------------------
#  What the admin screen lists
# ---------------------------------------------------------------------------

def inventory(cfg):
    """Everything that can be restricted, in the order the page shows it.

    [{key, label, kind, children:[{key,label}]}]
    """
    items = []

    for group, label in (("homepage", "Rail: Homepage"),
                         ("quickLinks", "Rail: Titan Systems"),
                         ("driverTools", "Rail: Driver Tools")):
        items.append({
            "key": "rail:" + group, "label": label, "kind": "rail",
            "children": [{"key": "link:%s::%s" % (group, i.get("n", "")),
                          "label": i.get("n", "")}
                         for i in cfg.get(group) or []],
        })

    for d in cfg.get("departments") or []:
        items.append({
            "key": "dept:" + d.get("id", ""), "label": d.get("name", ""),
            "kind": "department",
            "children": [{"key": doc_key(d.get("id", ""), x.get("n", "")),
                          "label": x.get("n", "")}
                         for x in d.get("docs") or []],
        })

    shared = cfg.get("yardDocs") or []
    for y in cfg.get("yards") or []:
        docs = y.get("docs") or shared
        items.append({
            "key": "yard:" + y.get("id", ""), "label": y.get("name", ""),
            "kind": "yard",
            "children": [{"key": doc_key(y.get("id", ""), x.get("n", "")),
                          "label": x.get("n", "")} for x in docs],
        })

    items.append({"key": "tool:orientation",
                  "label": "Orientation packet printing",
                  "kind": "tool", "children": []})

    for x in cfg.get("extraLibraries") or []:
        items.append({"key": "lib:" + x.get("name", ""),
                      "label": "Folder: " + x.get("name", ""),
                      "kind": "folder", "children": []})

    return items
