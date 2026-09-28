"""systems-access-v1: who may open which Titan site, managed from the intranet.

Every Titan site - tickets, dispatch, HR, accounts payable - asks the same two
tables whether a person may use it (titan_auth.may_use):

    portal.portal_sites    one row per site, by its short name (slug)
    portal.portal_access   one row per person per site

They belong to the portal, which was never put up, so until now the only way to
change them was SQL. This is the screen for them, on the intranet, behind the
intranet's own admin check. It writes exactly what the portal's screen would
have written, so if the portal is ever deployed the two agree.

Deliberately narrow:

  * people are added to and taken off a site that exists
  * a site can be added, and have its name, address and on/off changed
  * a site's short name is never changed - every app is configured by it, and
    renaming it would silently lock everybody out of that app
  * "open to everyone at Titan" is shown, and can be switched, but switching it
    ON asks for the site's short name typed out, because it opens that site to
    the whole tenant in one click
"""
import re

import titan_auth as auth

S = auth.PORTAL_SCHEMA                   # checked to be a plain identifier in titan_auth
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def emails_from(text):
    """A pasted list - commas, semicolons, spaces or new lines. Lower-cased,
    duplicates dropped, anything that is not an address left out."""
    out, seen = [], set()
    for chunk in re.split(r"[,\n;\s]+", text or ""):
        e = chunk.strip().lower()
        if e and EMAIL.match(e) and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def ready(conn):
    """Are the portal's tables there? The screen says so plainly if not."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS a, to_regclass(%s) AS b",
                    ("%s.portal_sites" % S, "%s.portal_access" % S))
        r = cur.fetchone()
    conn.rollback()
    return bool(r and r["a"] and r["b"])


def systems(conn):
    """Every site, in the portal's order, each with its people."""
    with conn.cursor() as cur:
        cur.execute("SELECT slug, name, url, blurb, badge, sort, live, open_to_all "
                    "FROM %s.portal_sites ORDER BY sort NULLS LAST, name" % S)
        sites = cur.fetchall()
        cur.execute("SELECT slug, email, granted_by, granted_at FROM %s.portal_access "
                    "ORDER BY email" % S)
        rows = cur.fetchall()
    conn.rollback()
    by = {}
    for r in rows:
        by.setdefault(r["slug"], []).append(r)
    return [dict(s, people=by.get(s["slug"], [])) for s in sites]


def _site(cur, slug):
    cur.execute("SELECT slug, open_to_all FROM %s.portal_sites WHERE slug = %%s" % S, (slug,))
    return cur.fetchone()


def grant(conn, slug, emails, by):
    """Give these people this site. -> how many were new."""
    n = 0
    with conn.cursor() as cur:
        if not _site(cur, slug):
            conn.rollback()
            raise ValueError("There is no site called %s." % slug)
        for e in emails:
            cur.execute("INSERT INTO %s.portal_access (slug, email, granted_by) SELECT %%s, %%s, %%s "
                        "WHERE NOT EXISTS (SELECT 1 FROM %s.portal_access WHERE slug = %%s AND email = %%s)"
                        % (S, S), (slug, e, by, slug, e))
            n += cur.rowcount
    conn.commit()
    return n


def revoke(conn, slug, email):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM %s.portal_access WHERE slug = %%s AND email = %%s" % S,
                    (slug, (email or "").strip().lower()))
        n = cur.rowcount
    conn.commit()
    return n


def add_site(conn, slug, name, url, blurb="", badge="", by=None):
    slug = (slug or "").strip().lower()
    if not SLUG.match(slug):
        raise ValueError("A short name is lower-case letters, digits and dashes, like titan-ap.")
    name, url = (name or "").strip(), (url or "").strip().rstrip("/")
    if not name or not re.match(r"^https://[a-z0-9.-]+(/.*)?$", url, re.I):
        raise ValueError("A new site needs a name, and an address starting https://.")
    with conn.cursor() as cur:
        if _site(cur, slug):
            conn.rollback()
            raise ValueError("There is already a site called %s." % slug)
        cur.execute("INSERT INTO %s.portal_sites (slug, name, url, blurb, badge, sort, live, open_to_all) "
                    "VALUES (%%s, %%s, %%s, %%s, %%s, 100, true, false)" % S,
                    (slug, name, url, (blurb or "").strip() or None, (badge or "").strip()[:3].upper() or None))
    conn.commit()


def set_site(conn, slug, name=None, url=None, live=None, open_to_all=None, confirm=""):
    """Change a site's name, address, on/off or open-to-everyone. Never its slug.
    Opening a site to everyone needs its slug typed out as `confirm`."""
    sets, args = [], []
    if name is not None:
        if not name.strip():
            raise ValueError("A site needs a name.")
        sets.append("name = %s"); args.append(name.strip())
    if url is not None:
        u = url.strip().rstrip("/")
        if not re.match(r"^https://[a-z0-9.-]+(/.*)?$", u, re.I):
            raise ValueError("The address has to start https://.")
        sets.append("url = %s"); args.append(u)
    if live is not None:
        sets.append("live = %s"); args.append(bool(live))
    with conn.cursor() as cur:
        s = _site(cur, slug)
        if not s:
            conn.rollback()
            raise ValueError("There is no site called %s." % slug)
        if open_to_all is not None:
            if open_to_all and not s["open_to_all"] and (confirm or "").strip().lower() != slug:
                conn.rollback()
                raise ValueError("To open %s to everyone at Titan, type its short name to confirm." % slug)
            sets.append("open_to_all = %s"); args.append(bool(open_to_all))
        if sets:
            cur.execute("UPDATE %s.portal_sites SET %s WHERE slug = %%s" % (S, ", ".join(sets)), args + [slug])
    conn.commit()
