"""systems-access-v1 tests: the Systems screen at /access/systems.

On a throwaway Postgres (pgserver) with the portal's two tables made the way
the portal makes them - never a real database. Skipped, not failed, where
pgserver is not installed.

What matters most is what must NOT happen: somebody who is not an intranet
administrator changing who gets into payroll or accounts payable, a site
opened to the whole company by one stray tick, or a site's short name - the
thing every app is configured by - being changed at all.

    python -m pytest test_systems_access.py -q
"""
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import systems_access as sa  # noqa: E402

ADMIN = "boss@tetransports.com"


def test_pasted_lists_are_read_the_way_people_paste_them():
    assert sa.emails_from("A@x.com, b@x.com;\nc@x.com  a@x.com not-an-email") == ["a@x.com", "b@x.com", "c@x.com"]
    assert sa.emails_from("") == []


# ---------------------------------------------------------------------------
#  Against a real Postgres
# ---------------------------------------------------------------------------
pgserver = pytest.importorskip("pgserver")


@pytest.fixture(scope="module")
def site():
    srv = pgserver.get_server(tempfile.mkdtemp(prefix="sysacc"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = srv.get_uri()
    os.environ.setdefault("SECRET_KEY", "test-only")
    os.environ["PORTAL_ADMINS"] = ADMIN
    import psycopg
    with psycopg.connect(srv.get_uri()) as c:
        c.execute("CREATE SCHEMA portal")
        c.execute("""CREATE TABLE portal.portal_sites (slug text PRIMARY KEY, open_to_all boolean DEFAULT false,
                     name text, url text, blurb text, badge text, sort int, live boolean DEFAULT true,
                     status_note text, added_at timestamptz DEFAULT now(), logo text)""")
        c.execute("""CREATE TABLE portal.portal_access (slug text NOT NULL, email text NOT NULL, granted_by text,
                     granted_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("INSERT INTO portal.portal_sites (slug, name, url, sort) VALUES "
                  "('titan-ap', 'Accounts Payable', 'https://ap.tetransports.com', 35), "
                  "('titan-hr', 'HR / Timesheets', 'https://tickets.tetransports.com/hr', 30)")
        c.commit()
    import intranet_access
    intranet_access.BREAKGLASS[:] = [ADMIN]
    import app as intranet
    intranet.app.config["TESTING"] = True
    yield intranet
    srv.cleanup() if hasattr(srv, "cleanup") else None


def client(intranet, email):
    cl = intranet.app.test_client()
    with cl.session_transaction() as s:
        s.update(office=True, email=email, name=email.split("@")[0])
    return cl


def access_rows(intranet, slug):
    with intranet.conn().cursor() as cur:
        cur.execute("SELECT email, granted_by FROM portal.portal_access WHERE slug = %s ORDER BY email", (slug,))
        rows = cur.fetchall()
    intranet.conn().rollback()
    return [(r["email"], r["granted_by"]) for r in rows]


def test_the_screen_lists_every_site_with_its_people(site):
    r = client(site, ADMIN).get("/access/systems")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Accounts Payable" in body and "HR / Timesheets" in body
    assert body.index("HR / Timesheets") < body.index("Accounts Payable")        # the portal's order


def test_the_intranet_access_page_links_to_it(site):
    assert 'href="/access/systems"' in client(site, ADMIN).get("/access").get_data(as_text=True)


def test_giving_access_takes_a_pasted_list_and_records_who_gave_it(site):
    r = client(site, ADMIN).post("/access/systems/titan-ap/grant",
                                 data={"emails": "Clerk@tetransports.com, second@tetransports.com"})
    assert r.status_code == 302 and "gave+access+to+2" in r.headers["Location"]
    assert access_rows(site, "titan-ap") == [("clerk@tetransports.com", ADMIN), ("second@tetransports.com", ADMIN)]


def test_the_same_person_twice_is_one_row(site):
    r = client(site, ADMIN).post("/access/systems/titan-ap/grant", data={"emails": "clerk@tetransports.com"})
    assert "already+had+it" in r.headers["Location"]
    assert [e for e, _ in access_rows(site, "titan-ap")].count("clerk@tetransports.com") == 1


def test_what_the_apps_check_sees_the_change(site):
    import titan_auth
    assert titan_auth.may_use(site.conn(), "clerk@tetransports.com", "titan-ap")
    client(site, ADMIN).post("/access/systems/titan-ap/revoke", data={"email": "clerk@tetransports.com"})
    assert not titan_auth.may_use(site.conn(), "clerk@tetransports.com", "titan-ap")


def test_somebody_who_is_not_an_admin_can_change_nothing(site):
    before = access_rows(site, "titan-hr")
    cl = client(site, "driver@tetransports.com")
    assert cl.get("/access/systems").status_code == 403
    assert cl.post("/access/systems/titan-hr/grant", data={"emails": "driver@tetransports.com"}).status_code == 403
    assert cl.post("/access/systems/add", data={"slug": "x", "name": "X", "url": "https://x.example"}).status_code == 403
    assert access_rows(site, "titan-hr") == before


def test_signed_out_is_not_let_in(site):
    r = site.app.test_client().get("/access/systems")
    assert r.status_code in (302, 401)


def test_opening_a_site_to_everyone_needs_its_name_typed(site):
    cl = client(site, ADMIN)
    r = cl.post("/access/systems/titan-hr/edit", data={"name": "HR / Timesheets", "url": "https://tickets.tetransports.com/hr",
                                                       "live": "on", "open_to_all": "on"})
    assert "err=" in r.headers["Location"]
    assert not [s for s in sa.systems(site.conn()) if s["slug"] == "titan-hr"][0]["open_to_all"]
    cl.post("/access/systems/titan-hr/edit", data={"name": "HR / Timesheets", "url": "https://tickets.tetransports.com/hr",
                                                  "live": "on", "open_to_all": "on", "confirm": "titan-hr"})
    assert [s for s in sa.systems(site.conn()) if s["slug"] == "titan-hr"][0]["open_to_all"]
    cl.post("/access/systems/titan-hr/edit", data={"name": "HR / Timesheets", "url": "https://tickets.tetransports.com/hr",
                                                  "live": "on"})
    assert not [s for s in sa.systems(site.conn()) if s["slug"] == "titan-hr"][0]["open_to_all"]    # closing needs no typing


def test_a_site_can_be_added_but_never_renamed(site):
    cl = client(site, ADMIN)
    r = cl.post("/access/systems/add", data={"slug": "bids", "name": "Bid Application", "url": "https://bids.tetransports.com"})
    assert "ok=" in r.headers["Location"]
    added = [s for s in sa.systems(site.conn()) if s["slug"] == "bids"][0]
    assert added["live"] and not added["open_to_all"]                                # closed by default
    assert "err=" in cl.post("/access/systems/add", data={"slug": "bids", "name": "Again",
                                                            "url": "https://bids.tetransports.com"}).headers["Location"]
    assert "err=" in cl.post("/access/systems/add", data={"slug": "Bad Name!", "name": "x",
                                                            "url": "https://x.example"}).headers["Location"]
    assert "err=" in cl.post("/access/systems/add", data={"slug": "plain", "name": "x",
                                                            "url": "http://not-https.example"}).headers["Location"]
    # The edit form has no slug field at all, and a forged one is ignored.
    cl.post("/access/systems/bids/edit", data={"slug": "renamed", "name": "Bids", "url": "https://bids.tetransports.com", "live": "on"})
    assert {s["slug"] for s in sa.systems(site.conn())} >= {"bids"} and "renamed" not in {s["slug"] for s in sa.systems(site.conn())}


def test_an_unknown_site_is_refused(site):
    r = client(site, ADMIN).post("/access/systems/nope/grant", data={"emails": "a@tetransports.com"})
    assert "err=" in r.headers["Location"]


def test_names_and_addresses_are_shown_as_text_not_html(site):
    with site.conn().cursor() as cur:
        cur.execute("UPDATE portal.portal_sites SET name = %s WHERE slug = 'bids'", ("<script>alert(1)</script>",))
    site.conn().commit()
    body = client(site, ADMIN).get("/access/systems").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body and "&lt;script&gt;" in body
