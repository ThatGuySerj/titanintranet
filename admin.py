"""admin-site-v1 (13 Oct 2026): intranet.tetransports.com/admin - one place to
see and fix every Titan site, from a desk or a phone.

Only the people in ADMIN_SITE_USERS get in (Serj and Derek to begin with).
Nobody else - not the intranet's own admins, not PORTAL_ADMINS. It can change
who gets into payroll and accounts payable, so the list is short on purpose and it fails closed: an empty or unreadable list
lets nobody in.

What is on it:

  Overview   every site up or down, the mailboxes, the OCR queue, the tray, the
             dispatch feed, the database - each with how long ago
  Access     who may open which site (the portal tables every site checks),
             the portal admins, the intranet's groups
  Scans &    re-check the mail and run the queue now, retry or cancel an OCR
  mail       job, put back a discarded scan, re-read an AP mailbox from a time
  Restore    put back AP invoices from the backups taken before a clean-out,
             reopen a voided invoice
  Database   size, connections, what is stuck, which queries move the most data
  Activity   what changed recently, across the sites, and this page's own log

Every change made here is written to intranet_admin_log with who and when.
Every POST needs the page's own header (X-Requested-With: fetch) and, where
the browser sends one, an Origin of this site - a form on another site can do
neither.

The ticket, AP and dispatch tables are read and written in their own schemas
(ocr, ap, dispatch by default); a section whose tables are not there says so
and the rest of the page still works.
"""
import datetime
import functools
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, Response, jsonify, request, session

import intranet_access
import systems_access
import titan_auth as auth

DEFAULT_ADMINS = "swahl@tetransports.com,dboothe@tetransports.com"
T = (os.environ.get("ADMIN_TICKETS_SCHEMA") or "ocr").strip()
AP = (os.environ.get("ADMIN_AP_SCHEMA") or "ap").strip()
DISP = (os.environ.get("ADMIN_DISPATCH_SCHEMA") or "dispatch").strip()
P = auth.PORTAL_SCHEMA
for _s in (T, AP, DISP):
    if not re.match(r"^[a-z_][a-z0-9_]*$", _s):
        raise RuntimeError("schema names are plain identifiers")

HEALTH = [("Tickets", "https://tickets.tetransports.com/healthz"),
          ("Accounts payable", "https://ap.tetransports.com/healthz"),
          ("Dispatch board", "https://dispatch.tetransports.com/api/health"),
          ("Website", "https://www.tetransports.com/")]

LOG_SQL = """CREATE TABLE IF NOT EXISTS intranet_admin_log (
    id     bigserial PRIMARY KEY,
    at     timestamptz NOT NULL DEFAULT now(),
    who    text NOT NULL,
    area   text NOT NULL,
    action text NOT NULL,
    target text,
    detail jsonb NOT NULL DEFAULT '{}'
);
-- security-v1: never readable through Supabase's public API; this site reads
-- it as the database owner, which row security does not stop.
ALTER TABLE intranet_admin_log ENABLE ROW LEVEL SECURITY"""


# Supabase's own connections: background workers (the pg_cron scheduler), its
# service logins, and its services by name. Shown, but never offered an End.
SYSTEM_SQL = """(backend_type <> 'client backend'
     OR usename IN ('supabase_admin', 'supabase_storage_admin', 'supabase_auth_admin',
                    'supabase_realtime_admin', 'supabase_replication_admin', 'authenticator',
                    'pgbouncer', 'supabase_read_only_user')
     OR application_name ~* '^(pg_cron|pg_net|postgrest|supabase|pgbouncer|realtime|gotrue|storage)')"""


def admins():
    raw = os.environ.get("ADMIN_SITE_USERS")
    raw = DEFAULT_ADMINS if raw is None else raw
    return {e.strip().lower() for e in raw.split(",") if "@" in e}


def health_targets():
    """ADMIN_HEALTH_URLS='Name=https://...,Name=https://...' replaces the list."""
    raw = (os.environ.get("ADMIN_HEALTH_URLS") or "").strip()
    if not raw:
        return list(HEALTH)
    out = []
    for item in raw.split(","):
        name, _, url = item.partition("=")
        if url.strip().startswith("https://"):
            out.append((name.strip(), url.strip()))
    return out


class Refused(Exception):
    pass


def make(protected, conn, who, html):
    """The blueprint, built with the intranet's own sign-in, connection and
    page helpers (passed in rather than imported, so app.py stays the one
    place they live)."""
    bp = Blueprint("admin", __name__, url_prefix="/admin")
    state = {"log_ready": False}

    # -- helpers ------------------------------------------------------------
    def q(sql, args=(), one=False):
        c = conn()
        try:
            with c.cursor() as cur:
                cur.execute(sql, args or None)
                rows = cur.fetchall() if cur.description else []
            c.rollback()
        except Exception:
            c.rollback()
            raise
        rows = [dict(r) for r in rows]
        return (rows[0] if rows else None) if one else rows

    def section(fn):
        """One part of a page: its error is its own, the rest still answers."""
        try:
            return fn()
        except Exception as e:
            try:
                conn().rollback()
            except Exception:
                pass
            return {"error": str(e).split("\n")[0][:240]}

    def log(area, action, target="", detail=None):
        c = conn()
        with c.cursor() as cur:
            if not state["log_ready"]:
                cur.execute(LOG_SQL)
                state["log_ready"] = True
            cur.execute("INSERT INTO intranet_admin_log (who, area, action, target, detail) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (who() or "?", area, action, (target or "")[:300], json.dumps(detail or {}, default=str)))
        c.commit()

    def body():
        return request.get_json(silent=True) or {}

    def gate(fn):
        """Signed in (the intranet's own check), on the list, and for a change,
        from this page."""
        @functools.wraps(fn)
        @protected
        def go(*a, **kw):
            email = (who() or "").strip().lower()
            if not email or email not in admins():
                if request.path.startswith("/admin/api"):
                    return jsonify(ok=False, error="this is for the Titan admins only"), 403
                return html("<!doctype html><meta charset=utf-8><meta name=viewport "
                            "content='width=device-width,initial-scale=1'><title>Admin</title>"
                            "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:520px;margin:14vh auto;"
                            "padding:0 22px;color:#1f2430}a{color:#243090}</style>"
                            "<h1>This page is for the Titan admins</h1><p>You are signed in as <b>%s</b>.</p>"
                            "<p><a href='/'>Back to the intranet</a></p>"
                            % (email or "nobody").replace("<", "&lt;"), 403)
            if request.method != "GET":
                if request.headers.get("X-Requested-With") != "fetch":
                    return jsonify(ok=False, error="that request did not come from the admin page"), 403
                origin = request.headers.get("Origin")
                if origin and urllib.parse.urlparse(origin).netloc != request.host:
                    return jsonify(ok=False, error="that request came from another site"), 403
            try:
                return fn(*a, **kw)
            except (Refused, ValueError) as e:
                try:
                    conn().rollback()
                except Exception:
                    pass
                return jsonify(ok=False, error=str(e)[:300]), 409
        return go

    # -- the page -----------------------------------------------------------
    @bp.get("")
    @bp.get("/")
    @gate
    def page():
        import admin_page
        return html(admin_page.HTML.replace("__ME__", json.dumps(
            {"email": who(), "name": session.get("name") or who()}).replace("<", "\\u003c")))

    # -- overview -----------------------------------------------------------
    def _probe(name, url, out):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "titan-admin/1"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read(4000)
                st = r.status
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read(4000)
        except Exception as e:
            out.append({"name": name, "url": url, "ok": False, "status": None, "ms": int((time.time() - t0) * 1000),
                        "detail": str(e)[:160]})
            return
        detail = {}
        try:
            j = json.loads(raw)
            detail = {k: j[k] for k in ("site", "commit", "build", "mail", "version", "oldest_h", "missing", "error")
                      if k in j}
        except ValueError:
            pass
        # A signed-in-only page answering 401/302 is up; 5xx or nothing is not.
        out.append({"name": name, "url": url, "ok": st is not None and st < 500, "status": st,
                    "ms": int((time.time() - t0) * 1000), "detail": detail})

    @bp.get("/api/overview")
    @gate
    def overview():
        probes = []
        threads = [threading.Thread(target=_probe, args=(n, u, probes)) for n, u in health_targets()]
        for th in threads:
            th.start()
        out = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        out["database"] = section(lambda: q(
            """SELECT pg_size_pretty(pg_database_size(current_database())) AS size,
                      (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections,
                      (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()
                         AND state = 'idle in transaction'
                         AND now() - state_change > interval '2 minutes') AS stuck""", one=True))
        out["tickets"] = section(lambda: dict(
            jobs=q("""SELECT state, count(*) AS n FROM %s.jobs
                      WHERE queued_at > now() - interval '24 hours' OR state IN ('queued', 'running')
                      GROUP BY state""" % T),
            waiting=q("""SELECT count(*) AS n, min(run_after) AS next FROM %s.jobs WHERE state = 'queued'""" % T,
                      one=True),
            last_failed=q("""SELECT id, finished_at, left(error, 200) AS error FROM %s.jobs WHERE state = 'failed'
                             ORDER BY finished_at DESC NULLS LAST LIMIT 1""" % T, one=True),
            tray=q("""SELECT count(*) AS n, min(created_at) AS oldest FROM %s.packets
                      WHERE state = 'sorting'""" % T, one=True),
            mail=q("""SELECT ok, checked_at, waiting, left(detail::text, 200) AS detail,
                             extract(epoch from now() - checked_at)::int AS age_s
                      FROM %s.mail_health WHERE id = 1""" % T, one=True),
            last_batch=q("SELECT batch_id, added_at FROM %s.batches ORDER BY added_at DESC LIMIT 1" % T, one=True)))
        out["ap"] = section(lambda: dict(
            mailboxes=_ap_mailboxes(),
            waiting=q("""SELECT count(*) FILTER (WHERE status IN ('new', 'flagged')) AS to_review,
                                count(*) FILTER (WHERE status = 'reviewed') AS ready_for_qb,
                                count(*) FILTER (WHERE (vendor_id IS NULL OR split_open)
                                                   AND status IN ('new', 'flagged')) AS tray
                         FROM %s.bills WHERE sample = 'real' AND kind <> 'statement'""" % AP, one=True)))
        out["dispatch"] = section(lambda: dict(
            tanks=q("""SELECT max(ts) AS last_reading, max(inserted_at) AS last_stored,
                              extract(epoch from now() - max(inserted_at))::int AS age_s
                       FROM %s.tank_reading""" % DISP, one=True),
            board_push=q("""SELECT batch_id, pushed_at, who, ok, mode FROM %s.board_pushes
                            ORDER BY id DESC LIMIT 1""" % T, one=True)))
        for th in threads:
            th.join(10)
        out["sites"] = sorted(probes, key=lambda p: [n for n, _ in health_targets()].index(p["name"])
                              if p["name"] in [n for n, _ in health_targets()] else 99)
        out["sites"].insert(0, {"name": "Intranet (this site)", "url": request.host_url, "ok": True,
                                "status": 200, "ms": 0, "detail": {}})
        return jsonify(ok=True, **out)

    def _ap_mailboxes():
        rows = q("""SELECT key, value FROM %s.schema_state
                    WHERE key LIKE 'mail_last%%' OR key LIKE 'mail_after%%'""" % AP)
        boxes = {}
        for r in rows:
            k = r["key"]
            kind, _, user = k.partition(":")
            b = boxes.setdefault(user or "(main mailbox)", {"mailbox": user or "(main mailbox)"})
            if kind == "mail_last":
                try:
                    b.update(last=json.loads(r["value"]))
                except ValueError:
                    b.update(last={"raw": r["value"][:200]})
            elif kind == "mail_after":
                b["reading_from"] = r["value"]
        return sorted(boxes.values(), key=lambda b: b["mailbox"])

    # -- access -------------------------------------------------------------
    @bp.get("/api/access")
    @gate
    def access():
        c = conn()
        out = {"ok": True}
        out["sites"] = section(lambda: systems_access.systems(c))
        out["portal_admins"] = section(lambda: q("SELECT email, added_by, added_at FROM %s.portal_admins "
                                                 "ORDER BY email" % P))
        out["breakglass"] = sorted(e for e in (os.environ.get("PORTAL_ADMINS") or "").lower().replace(" ", "")
                                   .split(",") if e)
        out["admin_site_users"] = sorted(admins())

        def groups():
            g = intranet_access.all_groups(c)
            m = intranet_access.all_members(c)
            c.rollback()
            return {"groups": g, "members": [{"email": e, "groups": sorted(gs)} for e, gs in sorted(m.items())]}
        out["intranet"] = section(groups)
        out["people"] = section(lambda: q("""SELECT email, name, last_at FROM %s.portal_people
                                             ORDER BY last_at DESC NULLS LAST LIMIT 300""" % P))
        return jsonify(out)

    @bp.post("/api/access/grant")
    @gate
    def access_grant():
        b = body()
        slug = (b.get("slug") or "").strip().lower()
        emails = systems_access.emails_from(b.get("emails") or "")
        if not emails:
            raise Refused("give at least one email address")
        n = systems_access.grant(conn(), slug, emails, who())
        log("access", "grant", slug, {"emails": emails, "new": n})
        return jsonify(ok=True, added=n)

    @bp.post("/api/access/revoke")
    @gate
    def access_revoke():
        b = body()
        slug, email = (b.get("slug") or "").strip().lower(), (b.get("email") or "").strip().lower()
        if email == (who() or "").lower() and slug in ("intranet",):
            raise Refused("you cannot take yourself off the intranet from here")
        n = systems_access.revoke(conn(), slug, email)
        log("access", "revoke", slug, {"email": email, "removed": n})
        return jsonify(ok=True, removed=n)

    @bp.post("/api/access/site")
    @gate
    def access_site():
        b = body()
        slug = (b.get("slug") or "").strip().lower()
        if b.get("new"):
            systems_access.add_site(conn(), slug, b.get("name"), b.get("url"), b.get("blurb") or "",
                                    b.get("badge") or "", by=who())
            log("access", "add site", slug, {"name": b.get("name"), "url": b.get("url")})
            return jsonify(ok=True)
        systems_access.set_site(conn(), slug, name=b.get("name"), url=b.get("url"),
                                live=b.get("live") if "live" in b else None,
                                open_to_all=b.get("open_to_all") if "open_to_all" in b else None,
                                confirm=b.get("confirm") or "")
        log("access", "edit site", slug, {k: b[k] for k in ("name", "url", "live", "open_to_all") if k in b})
        return jsonify(ok=True)

    @bp.post("/api/access/portal-admin")
    @gate
    def access_portal_admin():
        b = body()
        email = intranet_access.clean_email(b.get("email"))
        if not email:
            raise Refused("that does not look like an email address")
        c = conn()
        with c.cursor() as cur:
            if b.get("remove"):
                cur.execute("DELETE FROM %s.portal_admins WHERE email = %%s" % P, (email,))
            else:
                cur.execute("INSERT INTO %s.portal_admins (email, added_by) VALUES (%%s, %%s) "
                            "ON CONFLICT DO NOTHING" % P, (email, who()))
        c.commit()
        log("access", "portal admin " + ("remove" if b.get("remove") else "add"), email)
        return jsonify(ok=True)

    @bp.post("/api/access/intranet")
    @gate
    def access_intranet():
        b = body()
        email = intranet_access.clean_email(b.get("email"))
        if not email:
            raise Refused("that does not look like an email address")
        groups = [g for g in (b.get("groups") or []) if isinstance(g, str)]
        if groups:
            intranet_access.set_member_groups(conn(), email, groups, by=who())
        else:
            intranet_access.drop_member(conn(), email)
        log("access", "intranet groups", email, {"groups": groups})
        return jsonify(ok=True)

    # -- mail & OCR ---------------------------------------------------------
    @bp.get("/api/work")
    @gate
    def work():
        out = {"ok": True}
        out["jobs"] = section(lambda: q(
            """SELECT id, kind, state, batch_id, attempts, pages_done, pages_total, cost_usd,
                      queued_at, started_at, finished_at, run_after, left(error, 300) AS error,
                      left(coalesce(payload->>'subject', payload->>'filename', ''), 120) AS subject
               FROM %s.jobs ORDER BY id DESC LIMIT 40""" % T))
        out["requests"] = section(lambda: q("SELECT kind, asked_by, asked_at, taken_at FROM %s.worker_requests "
                                            "ORDER BY asked_at DESC" % T))
        out["mail"] = section(lambda: q("""SELECT ok, checked_at, folder, waiting, left(detail::text, 300) AS detail
                                           FROM %s.mail_health WHERE id = 1""" % T, one=True))
        out["discarded"] = section(lambda: q(
            """SELECT id, filename, pages, tickets, resolved_at, resolved_by, created_at
               FROM %s.packets WHERE state = 'discarded' ORDER BY resolved_at DESC NULLS LAST LIMIT 25""" % T))
        out["tray"] = section(lambda: q("""SELECT id, filename, pages, tickets, created_at FROM %s.packets
                                           WHERE state = 'sorting' ORDER BY created_at LIMIT 50""" % T))
        out["ap_mailboxes"] = section(_ap_mailboxes)
        out["ap_problems"] = section(lambda: q(
            """SELECT message_id, seen_at, note FROM %s.mail_seen
               WHERE note LIKE 'could not be read%%' OR note LIKE 'stopped part way%%' OR note LIKE 'left out%%'
               ORDER BY seen_at DESC LIMIT 30""" % AP))
        return jsonify(out)

    @bp.post("/api/work/run-now")
    @gate
    def work_run_now():
        c = conn()
        with c.cursor() as cur:
            for kind in ("poll", "run"):
                cur.execute("""INSERT INTO %s.worker_requests (kind, asked_by) VALUES (%%s, %%s)
                               ON CONFLICT (kind) DO UPDATE SET asked_at = now(), asked_by = EXCLUDED.asked_by,
                                 taken_at = NULL""" % T, (kind, who()))
        c.commit()
        log("work", "tickets: check mail and run now", "")
        return jsonify(ok=True)

    @bp.post("/api/work/job")
    @gate
    def work_job():
        b = body()
        jid, act = int(b.get("id") or 0), b.get("action")
        c = conn()
        with c.cursor() as cur:
            if act == "retry":
                cur.execute("""UPDATE %s.jobs SET state = 'queued', run_after = now(), error = NULL,
                                 started_at = NULL, finished_at = NULL
                               WHERE id = %%s AND state IN ('failed', 'cancelled')""" % T, (jid,))
            elif act == "cancel":
                cur.execute("UPDATE %s.jobs SET state = 'cancelled', finished_at = now() "
                            "WHERE id = %%s AND state = 'queued'" % T, (jid,))
            elif act == "now":
                cur.execute("UPDATE %s.jobs SET run_after = now() WHERE id = %%s AND state = 'queued'" % T, (jid,))
            else:
                raise Refused("retry, cancel or now")
            n = cur.rowcount
        c.commit()
        if not n:
            raise Refused("that job is not in a state that allows it - refresh")
        log("work", "job " + act, str(jid))
        return jsonify(ok=True)

    @bp.post("/api/work/packet-restore")
    @gate
    def work_packet_restore():
        pid = int(body().get("id") or 0)
        c = conn()
        with c.cursor() as cur:
            cur.execute("""UPDATE %s.packets SET state = 'sorting', resolved_at = NULL, resolved_by = NULL
                           WHERE id = %%s AND state = 'discarded'""" % T, (pid,))
            n = cur.rowcount
        c.commit()
        if not n:
            raise Refused("that scan is not discarded any more - refresh")
        log("work", "scan back to the tray", str(pid))
        return jsonify(ok=True)

    @bp.post("/api/work/ap-reread")
    @gate
    def work_ap_reread():
        """Start an AP mailbox's next check from N hours ago. Emails already
        taken are skipped by their id, so nothing is filed twice; ones that
        were let go (failed, or forgotten below) are read again."""
        b = body()
        hours = int(b.get("hours") or 0)
        if not 1 <= hours <= 24 * 14:
            raise Refused("between 1 hour and 14 days")
        box = (b.get("mailbox") or "").strip().lower()
        key = "mail_after" if box in ("", "(main mailbox)") else "mail_after:" + box
        when = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        c = conn()
        with c.cursor() as cur:
            cur.execute("""INSERT INTO %s.schema_state (key, value) VALUES (%%s, %%s)
                           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""" % AP, (key, when))
        c.commit()
        log("work", "AP mailbox re-read", box or "(main)", {"from": when})
        return jsonify(ok=True, reading_from=when)

    @bp.post("/api/work/ap-forget")
    @gate
    def work_ap_forget():
        mid = (body().get("message_id") or "").strip()
        c = conn()
        with c.cursor() as cur:
            cur.execute("DELETE FROM %s.mail_seen WHERE message_id = %%s" % AP, (mid,))
            n = cur.rowcount
        c.commit()
        if not n:
            raise Refused("that email is not on the list any more")
        log("work", "AP email forgotten (will be read again)", mid)
        return jsonify(ok=True)

    # -- restore ------------------------------------------------------------
    @bp.get("/api/restore")
    @gate
    def restore():
        out = {"ok": True}

        def backups():
            rows = q("""SELECT table_schema AS schema, table_name AS name FROM information_schema.tables
                        WHERE table_schema LIKE 'ap\\_backup\\_%%' ORDER BY 1, 2""")
            sets = {}
            for r in rows:
                m = re.match(r"^(tray_)?bills$", r["name"])
                if not m:
                    continue
                n = q('SELECT count(*) AS n, min(created_at) AS first, max(created_at) AS last '
                      'FROM "%s"."%s"' % (r["schema"], r["name"]), one=True)
                back = q('SELECT count(*) AS n FROM "%s"."%s" b WHERE EXISTS (SELECT 1 FROM %s.bills x '
                         'WHERE x.id = b.id)' % (r["schema"], r["name"], AP), one=True)
                sets.setdefault(r["schema"], []).append(
                    {"set": "tray" if m.group(1) else "invoices", "table": r["name"], "rows": n["n"],
                     "first": n["first"], "last": n["last"], "already_back": back["n"]})
            return [{"schema": s, "sets": v} for s, v in sets.items()]
        out["ap_backups"] = section(backups)
        out["ap_voided"] = section(lambda: q(
            """SELECT b.id, b.bill_number, b.total, b.updated_at, left(b.note, 160) AS note, v.name AS vendor
               FROM %s.bills b LEFT JOIN %s.vendors v ON v.id = b.vendor_id
               WHERE b.sample = 'real' AND b.status = 'void' ORDER BY b.updated_at DESC LIMIT 30""" % (AP, AP)))
        return jsonify(out)

    @bp.post("/api/restore/ap-backup")
    @gate
    def restore_ap_backup():
        b = body()
        schema, which = (b.get("schema") or ""), (b.get("set") or "")
        if not re.match(r"^ap_backup_[0-9a-z_]+$", schema) or which not in ("invoices", "tray"):
            raise Refused("which backup?")
        if (b.get("confirm") or "").strip().lower() != "restore":
            raise Refused('type "restore" to confirm')
        pre = "tray_" if which == "tray" else ""
        tables = [("documents", "%sdocuments" % pre), ("bills", "%sbills" % pre),
                  ("bill_lines", "%sbill_lines" % pre), ("bill_holds", "%sbill_holds" % pre),
                  ("payments", "%spayments" % pre)]
        c = conn()
        done = {}
        with c.cursor() as cur:
            for live, bk in tables:
                cur.execute("SELECT to_regclass(%s) AS t", ('"%s"."%s"' % (schema, bk),))
                if not cur.fetchone()["t"]:
                    continue
                # By column name: the live table may have gained columns since
                # the backup was taken (documents.file_sha256 did).
                cur.execute("""SELECT b.column_name AS c FROM information_schema.columns b
                               JOIN information_schema.columns l ON l.table_schema = %s AND l.table_name = %s
                                AND l.column_name = b.column_name
                               WHERE b.table_schema = %s AND b.table_name = %s ORDER BY b.ordinal_position""",
                            (AP, live, schema, bk))
                cols = ", ".join('"%s"' % r["c"] for r in cur.fetchall())
                if not cols:
                    continue
                cur.execute('INSERT INTO %s.%s (%s) SELECT %s FROM "%s"."%s" ON CONFLICT DO NOTHING'
                            % (AP, live, cols, cols, schema, bk))
                done[live] = cur.rowcount
        c.commit()
        log("restore", "AP backup put back", "%s %s" % (schema, which), done)
        return jsonify(ok=True, restored=done)

    @bp.post("/api/restore/ap-unvoid")
    @gate
    def restore_ap_unvoid():
        bid = int(body().get("id") or 0)
        c = conn()
        with c.cursor() as cur:
            cur.execute("UPDATE %s.bills SET status = 'new', updated_at = now() WHERE id = %%s AND status = 'void' "
                        "AND sample = 'real'" % AP, (bid,))
            n = cur.rowcount
        c.commit()
        if not n:
            raise Refused("that invoice is not voided any more")
        log("restore", "AP invoice reopened", str(bid))
        return jsonify(ok=True)

    # -- database -----------------------------------------------------------
    @bp.get("/api/database")
    @gate
    def database():
        out = {"ok": True}
        out["schemas"] = section(lambda: q(
            """SELECT n.nspname AS schema, pg_size_pretty(sum(pg_total_relation_size(c.oid))::bigint) AS size,
                      sum(pg_total_relation_size(c.oid))::bigint AS bytes
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE c.relkind IN ('r', 'm') AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
               GROUP BY 1 ORDER BY 3 DESC LIMIT 15"""))
        out["tables"] = section(lambda: q(
            """SELECT n.nspname || '.' || c.relname AS name, pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
                      c.reltuples::bigint AS rows
               FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
               ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 15"""))
        out["connections"] = section(lambda: q(
            """SELECT pid, usename AS who, application_name AS app, state,
                      extract(epoch from now() - coalesce(state_change, backend_start))::int AS for_s,
                      left(query, 160) AS query, %s AS system
               FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()
               ORDER BY (state = 'idle in transaction') DESC, state_change NULLS LAST LIMIT 40""" % SYSTEM_SQL))
        out["heavy"] = section(lambda: q(
            """SELECT calls, rows, round(rows::numeric / greatest(calls, 1)) AS rows_per_call,
                      round(total_exec_time / 1000) AS seconds, left(regexp_replace(query, '\\s+', ' ', 'g'), 180) AS query
               FROM pg_stat_statements ORDER BY rows DESC LIMIT 10"""))
        return jsonify(out)

    @bp.post("/api/database/end")
    @gate
    def database_end():
        """End one stuck connection: idle in a transaction for over a minute, or
        one query running over five minutes. Its own work is rolled back;
        nothing else is touched.

        Never Supabase's own (SYSTEM_SQL). Those sit idle for days by design -
        the cron scheduler, pg_net, PostgREST, the pooler - and "idle for a
        long time" is not stuck: an idle connection holds nothing. v1 offered
        to end anything over five minutes in any state, which put an End
        button on every one of them."""
        pid = int(body().get("pid") or 0)
        row = q("""SELECT pid, state, extract(epoch from now() - coalesce(state_change, backend_start))::int AS for_s,
                          %s AS system
                   FROM pg_stat_activity WHERE pid = %%s AND datname = current_database()""" % SYSTEM_SQL,
                (pid,), one=True)
        if not row:
            raise Refused("that connection has already gone")
        if row["system"]:
            raise Refused("that is one of Supabase's own connections - it is never ended from here")
        if not ((row["state"] == "idle in transaction" and row["for_s"] > 60)
                or (row["state"] == "active" and row["for_s"] > 300)):
            raise Refused("only a connection stuck in a transaction, or one query running over five minutes, "
                          "is ended here")
        ok = q("SELECT pg_terminate_backend(%s) AS ok", (pid,), one=True)
        log("database", "end connection", str(pid), dict(row))
        return jsonify(ok=True, ended=bool(ok and ok["ok"]))

    # -- activity -----------------------------------------------------------
    @bp.get("/api/activity")
    @gate
    def activity():
        out = {"ok": True}

        def mine():
            with conn().cursor() as cur:
                cur.execute(LOG_SQL)
            conn().commit()
            return q("SELECT at, who, area, action, target, detail FROM intranet_admin_log ORDER BY id DESC LIMIT 100")
        out["admin_log"] = section(mine)
        out["recent"] = section(lambda: q(
            """(SELECT granted_at AS at, granted_by AS who, 'Access' AS site,
                       'gave ' || email || ' ' || slug AS what FROM %(P)s.portal_access
                 WHERE granted_at > now() - interval '30 days')
               UNION ALL
               (SELECT reviewed_at, reviewed_by, 'AP', 'approved invoice ' || coalesce(bill_number, '#' || id)
                  FROM %(AP)s.bills WHERE sample = 'real' AND reviewed_at > now() - interval '7 days')
               UNION ALL
               (SELECT changed_at, changed_by, 'Tickets', action || ' slip ' || page_key || ' in ' || batch_id
                  FROM %(T)s.support_changes WHERE changed_at > now() - interval '7 days')
               UNION ALL
               (SELECT pushed_at, who, 'Dispatch', 'sent ' || batch_id || ' to the board (' || coalesce(mode, '') || ')'
                  FROM %(T)s.board_pushes WHERE pushed_at > now() - interval '7 days')
               ORDER BY 1 DESC NULLS LAST LIMIT 120""" % {"P": P, "AP": AP, "T": T}))
        return jsonify(out)

    return bp
