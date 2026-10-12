"""admin-site-v1 tests: /admin.

On a throwaway Postgres (pgserver) carrying small copies of the tables the
admin page reads from the other sites - never a real database. Nothing here
talks to the internet.

What matters most is what must NOT happen: anybody but the two admins getting
in, a change made by a form on another site, ending a connection that is not
stuck, and a restore that files something twice.

    python -m pytest test_admin.py -q
"""
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


SERJ, DEREK, OTHER = "swahl@tetransports.com", "dboothe@tetransports.com", "clerk@tetransports.com"


# ---------------------------------------------------------------------------
#  The routes, against a real Postgres
# ---------------------------------------------------------------------------
pgserver = pytest.importorskip("pgserver")

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS portal;
CREATE TABLE portal.portal_sites (slug text PRIMARY KEY, open_to_all boolean DEFAULT false, name text, url text,
  blurb text, badge text, sort int, live boolean DEFAULT true, status_note text, logo text, added_at timestamptz DEFAULT now());
CREATE TABLE portal.portal_access (slug text NOT NULL, email text NOT NULL, granted_by text,
  granted_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (slug, email));
CREATE TABLE portal.portal_admins (email text PRIMARY KEY, added_by text, added_at timestamptz DEFAULT now());
CREATE TABLE portal.portal_people (email text PRIMARY KEY, name text, first_at timestamptz, last_at timestamptz, seen int);
INSERT INTO portal.portal_sites (slug, name, url, sort) VALUES ('titan-ap', 'Accounts Payable', 'https://ap.tetransports.com', 1),
  ('tickets', 'Tickets', 'https://tickets.tetransports.com', 2);
CREATE SCHEMA IF NOT EXISTS ocr;
CREATE TABLE ocr.jobs (id bigserial PRIMARY KEY, kind text NOT NULL DEFAULT 'ocr', state text NOT NULL DEFAULT 'queued',
  payload jsonb NOT NULL DEFAULT '{}', batch_id text, run_after timestamptz, attempts int NOT NULL DEFAULT 0,
  pages_total int, pages_done int NOT NULL DEFAULT 0, cost_usd numeric, queued_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, finished_at timestamptz, error text);
CREATE TABLE ocr.packets (id bigserial PRIMARY KEY, filename text, pages int DEFAULT 0, tickets int DEFAULT 0,
  state text NOT NULL DEFAULT 'sorting', created_at timestamptz DEFAULT now(), resolved_at timestamptz, resolved_by text);
CREATE TABLE ocr.worker_requests (kind text PRIMARY KEY, asked_by text, asked_at timestamptz DEFAULT now(), taken_at timestamptz);
CREATE TABLE ocr.mail_health (id int PRIMARY KEY, ok boolean, checked_at timestamptz, folder text, waiting int, detail jsonb);
CREATE TABLE ocr.batches (batch_id text PRIMARY KEY, added_at timestamptz DEFAULT now());
CREATE TABLE ocr.board_pushes (id bigserial PRIMARY KEY, batch_id text, pushed_at timestamptz DEFAULT now(), who text,
  mode text, ok boolean DEFAULT true);
CREATE TABLE ocr.support_changes (id bigserial PRIMARY KEY, batch_id text, page_key text, action text,
  changed_by text, changed_at timestamptz DEFAULT now());
CREATE SCHEMA IF NOT EXISTS ap;
CREATE TABLE ap.schema_state (key text PRIMARY KEY, value text);
CREATE TABLE ap.vendors (id bigserial PRIMARY KEY, name text);
CREATE TABLE ap.documents (id bigserial PRIMARY KEY, filename text, sha256 text UNIQUE, file_sha256 text);
CREATE TABLE ap.bills (id bigserial PRIMARY KEY, sample text DEFAULT 'real', document_id bigint, vendor_id bigint,
  bill_number text, total numeric, status text DEFAULT 'new', kind text DEFAULT 'bill', split_open boolean DEFAULT false,
  note text, reviewed_by text, reviewed_at timestamptz, created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now());
CREATE TABLE ap.bill_lines (id bigserial PRIMARY KEY, bill_id bigint, amount numeric);
CREATE TABLE ap.bill_holds (bill_id bigint PRIMARY KEY, who text);
CREATE TABLE ap.payments (id bigserial PRIMARY KEY, bill_id bigint, amount numeric);
CREATE TABLE ap.mail_seen (message_id text PRIMARY KEY, seen_at timestamptz DEFAULT now(), documents int, note text);
CREATE SCHEMA ap_backup_20261009;
CREATE TABLE ap_backup_20261009.documents (id bigint, filename text, sha256 text);
CREATE TABLE ap_backup_20261009.bills (id bigint, sample text, document_id bigint, bill_number text, total numeric,
  status text, kind text, split_open boolean, created_at timestamptz);
CREATE TABLE ap_backup_20261009.bill_lines (id bigint, bill_id bigint, amount numeric);
INSERT INTO ap_backup_20261009.documents VALUES (900, 'old.pdf', 'sha-900'), (901, 'old2.pdf', 'sha-901');
INSERT INTO ap_backup_20261009.bills VALUES (900, 'real', 900, 'INV-900', 10, 'new', 'bill', false, now()),
  (901, 'real', 901, 'INV-901', 11, 'new', 'bill', false, now());
INSERT INTO ap_backup_20261009.bill_lines VALUES (9000, 900, 10);
"""


@pytest.fixture(scope="module")
def site():
    srv = pgserver.get_server(tempfile.mkdtemp(prefix="admintest"), cleanup_mode="stop")
    os.environ["DATABASE_URL"] = srv.get_uri()
    os.environ.setdefault("SECRET_KEY", "test-only")
    os.environ["ADMIN_HEALTH_URLS"] = "Nowhere=https://127.0.0.1:9/"     # refused at once, no network
    os.environ.pop("ADMIN_SITE_USERS", None)
    import psycopg
    with psycopg.connect(srv.get_uri()) as c:
        c.execute(SCHEMA)
        c.commit()
    import app as intranet
    old = getattr(intranet._local, "conn", None)
    if old is not None:
        old.close()
    intranet._local.conn = None
    intranet.app.config["TESTING"] = True
    yield intranet, srv.get_uri()
    old = getattr(intranet._local, "conn", None)
    if old is not None:
        old.close()
    intranet._local.conn = None


def client(intranet, email):
    cl = intranet.app.test_client()
    if email:
        with cl.session_transaction() as s:
            s.update(office=True, email=email, name=email.split("@")[0])
    return cl


H = {"X-Requested-With": "fetch"}


def sql(uri, q, *a):
    import psycopg
    with psycopg.connect(uri) as c:
        r = c.execute(q, a or None)
        rows = r.fetchall() if r.description else None
        c.commit()
    return rows


def test_only_serj_and_derek_get_in(site):
    intranet, _ = site
    assert client(intranet, SERJ).get("/admin").status_code == 200
    assert b"Titan Admin" in client(intranet, DEREK).get("/admin/").data
    r = client(intranet, OTHER).get("/admin")
    assert r.status_code == 403 and b"for the Titan admins" in r.data
    assert client(intranet, OTHER).get("/admin/api/overview").status_code == 403
    r = client(intranet, None).get("/admin/api/overview", headers=H)
    assert r.status_code in (302, 401)


def test_the_list_can_change_and_an_empty_list_lets_nobody_in(site, monkeypatch):
    intranet, _ = site
    monkeypatch.setenv("ADMIN_SITE_USERS", OTHER)
    assert client(intranet, OTHER).get("/admin").status_code == 200
    assert client(intranet, SERJ).get("/admin").status_code == 403
    monkeypatch.setenv("ADMIN_SITE_USERS", "")
    assert client(intranet, SERJ).get("/admin").status_code == 403


def test_a_change_needs_the_pages_header_and_this_sites_origin(site):
    intranet, uri = site
    cl = client(intranet, SERJ)
    assert cl.post("/admin/api/work/run-now", json={}).status_code == 403
    assert cl.post("/admin/api/work/run-now", json={},
                   headers=dict(H, Origin="https://evil.example")).status_code == 403
    assert sql(uri, "SELECT count(*) FROM ocr.worker_requests")[0][0] == 0
    r = cl.post("/admin/api/work/run-now", json={}, headers=H)
    assert r.status_code == 200
    assert sorted(x[0] for x in sql(uri, "SELECT kind FROM ocr.worker_requests")) == ["poll", "run"]


def test_the_overview_answers_even_with_a_site_missing(site):
    intranet, uri = site
    sql(uri, "INSERT INTO ocr.jobs (state, error, finished_at) VALUES ('failed', 'boom', now())")
    j = client(intranet, SERJ).get("/admin/api/overview").get_json()
    assert j["ok"] and j["tickets"]["jobs"] and j["tickets"]["last_failed"]["error"] == "boom"
    assert "error" in j["dispatch"]                       # no dispatch schema here: said, not a 500
    assert any(s["name"] == "Nowhere" and not s["ok"] for s in j["sites"])


def test_access_is_given_taken_and_logged(site):
    intranet, uri = site
    cl = client(intranet, SERJ)
    r = cl.post("/admin/api/access/grant", json={"slug": "titan-ap", "emails": "A@x.com, b@x.com"}, headers=H)
    assert r.get_json()["added"] == 2
    cl.post("/admin/api/access/revoke", json={"slug": "titan-ap", "email": "a@x.com"}, headers=H)
    assert [x[0] for x in sql(uri, "SELECT email FROM portal.portal_access WHERE slug='titan-ap'")] == ["b@x.com"]
    r = cl.post("/admin/api/access/site", json={"slug": "tickets", "open_to_all": True}, headers=H)
    assert r.status_code == 409                           # not without typing the slug
    r = cl.post("/admin/api/access/site", json={"slug": "tickets", "open_to_all": True, "confirm": "tickets"}, headers=H)
    assert r.status_code == 200 and sql(uri, "SELECT open_to_all FROM portal.portal_sites WHERE slug='tickets'")[0][0]
    cl.post("/admin/api/access/portal-admin", json={"email": "c@x.com"}, headers=H)
    assert sql(uri, "SELECT email FROM portal.portal_admins") == [("c@x.com",)]
    log = sql(uri, "SELECT who, action, target FROM intranet_admin_log ORDER BY id")
    assert (SERJ, "grant", "titan-ap") in log and (SERJ, "edit site", "tickets") in log
    acc = cl.get("/admin/api/access").get_json()
    assert any(s["slug"] == "titan-ap" for s in acc["sites"]) and SERJ in acc["admin_site_users"]


def test_ocr_jobs_and_the_tray(site):
    intranet, uri = site
    cl = client(intranet, SERJ)
    jid = sql(uri, "INSERT INTO ocr.jobs (state) VALUES ('failed') RETURNING id")[0][0]
    assert cl.post("/admin/api/work/job", json={"id": jid, "action": "cancel"}, headers=H).status_code == 409
    assert cl.post("/admin/api/work/job", json={"id": jid, "action": "retry"}, headers=H).status_code == 200
    assert sql(uri, "SELECT state FROM ocr.jobs WHERE id = %s", jid)[0][0] == "queued"
    pid = sql(uri, "INSERT INTO ocr.packets (filename, state, resolved_by) VALUES ('s.pdf', 'discarded', 'x') "
                   "RETURNING id")[0][0]
    assert cl.post("/admin/api/work/packet-restore", json={"id": pid}, headers=H).status_code == 200
    assert sql(uri, "SELECT state, resolved_by FROM ocr.packets WHERE id = %s", pid)[0] == ("sorting", None)
    w = cl.get("/admin/api/work").get_json()
    assert any(p["id"] == pid for p in w["tray"])


def test_an_ap_mailbox_is_read_again_from_a_time(site):
    intranet, uri = site
    cl = client(intranet, SERJ)
    sql(uri, "INSERT INTO ap.mail_seen (message_id, note) VALUES ('m1', 'could not be read: x')")
    r = cl.post("/admin/api/work/ap-reread", json={"mailbox": "titanoilap@tetransports.com", "hours": 24}, headers=H)
    assert r.status_code == 200
    assert sql(uri, "SELECT value FROM ap.schema_state WHERE key = 'mail_after:titanoilap@tetransports.com'")
    assert cl.post("/admin/api/work/ap-reread", json={"hours": 9999}, headers=H).status_code == 409
    assert cl.post("/admin/api/work/ap-forget", json={"message_id": "m1"}, headers=H).status_code == 200
    assert sql(uri, "SELECT count(*) FROM ap.mail_seen")[0][0] == 0


def test_a_backup_is_put_back_once_by_column_name(site):
    intranet, uri = site
    cl = client(intranet, SERJ)
    sql(uri, "INSERT INTO ap.documents (id, filename, sha256) VALUES (901, 'old2.pdf', 'sha-901')")
    sql(uri, "INSERT INTO ap.bills (id, document_id, bill_number) VALUES (901, 901, 'INV-901')")
    r = cl.post("/admin/api/restore/ap-backup", json={"schema": "ap_backup_20261009", "set": "invoices"}, headers=H)
    assert r.status_code == 409                            # not without "restore" typed
    r = cl.post("/admin/api/restore/ap-backup", json={"schema": "ap_backup_20261009", "set": "invoices",
                                                       "confirm": "restore"}, headers=H)
    assert r.status_code == 200 and r.get_json()["restored"]["bills"] == 1   # 901 was already there
    assert sql(uri, "SELECT count(*) FROM ap.bills WHERE id IN (900, 901)")[0][0] == 2
    assert sql(uri, "SELECT count(*) FROM ap.bill_lines WHERE id = 9000")[0][0] == 1
    cl.post("/admin/api/restore/ap-backup", json={"schema": "ap_backup_20261009", "set": "invoices",
                                                   "confirm": "restore"}, headers=H)
    assert sql(uri, "SELECT count(*) FROM ap.bills WHERE id = 900")[0][0] == 1     # again: nothing doubled
    assert cl.post("/admin/api/restore/ap-backup", json={"schema": "public; drop", "set": "invoices",
                                                          "confirm": "restore"}, headers=H).status_code == 409
    sql(uri, "UPDATE ap.bills SET status = 'void' WHERE id = 900")
    rs = cl.get("/admin/api/restore").get_json()
    assert any(v["id"] == 900 for v in rs["ap_voided"]) and rs["ap_backups"][0]["sets"]
    assert cl.post("/admin/api/restore/ap-unvoid", json={"id": 900}, headers=H).status_code == 200
    assert sql(uri, "SELECT status FROM ap.bills WHERE id = 900")[0][0] == "new"


def test_database_and_activity_answer(site):
    intranet, _ = site
    cl = client(intranet, SERJ)
    d = cl.get("/admin/api/database").get_json()
    assert d["ok"] and isinstance(d["schemas"], list) and "heavy" in d
    a = cl.get("/admin/api/activity").get_json()
    assert a["ok"] and a["admin_log"]


def test_every_page_carries_the_security_headers_and_a_locked_cookie(site):
    """security-headers-v1"""
    intranet, _ = site
    r = client(intranet, SERJ).get("/admin")
    assert r.headers["Strict-Transport-Security"].startswith("max-age=")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    cfg = intranet.app.config
    assert cfg["SESSION_COOKIE_SECURE"] and cfg["SESSION_COOKIE_HTTPONLY"] and cfg["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_an_idle_connection_is_never_ended_and_one_mid_change_is(site):
    """Idle for days is how Supabase's own connections - and every site's
    pooled ones - work; an idle connection holds nothing. Only one stuck in a
    transaction (or running one query for over five minutes) may be ended."""
    import time
    import psycopg
    intranet, uri = site
    cl = client(intranet, SERJ)
    idle = psycopg.connect(uri, application_name="pg_cron scheduler test")
    stuck = psycopg.connect(uri, application_name="some-site")
    try:
        idle.execute("SELECT 1")
        idle.commit()
        stuck.execute("SELECT 1")              # a transaction left open
        time.sleep(1.2)
        pid_idle, pid_stuck = idle.info.backend_pid, stuck.info.backend_pid
        rows = {c["pid"]: c for c in cl.get("/admin/api/database").get_json()["connections"]}
        assert rows[pid_idle]["system"] and not rows[pid_stuck]["system"]

        r = cl.post("/admin/api/database/end", json={"pid": pid_idle}, headers=H)
        assert r.status_code == 409 and "Supabase" in r.get_json()["error"]
        r = cl.post("/admin/api/database/end", json={"pid": pid_stuck}, headers=H)
        assert r.status_code == 409                # stuck, but not for a minute yet
        sql(uri, "SELECT 1")                       # nothing else was touched
    finally:
        idle.close()
        stuck.close()
