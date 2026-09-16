"""The Titan Enterprises intranet.

    gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app

Its own site, its own repository, its own Azure Web App. It was part of the
ticket app for a fortnight and that was the wrong shape: one process meant one
restart, so renaming a link on the noticeboard took the site people file
tickets in down with it.

What it serves:

    /                 the intranet, built per person
    /images/<name>    the logos
    /access           who sees what - administrators only
    /api/orientation  the packet folders and their files
    /api/print-packets    the chosen packets, merged into one PDF

`titan_auth.py` is a COPY of the shared sign-in module, which is how every
Titan site carries it - the portal's README explains why: these are separate
repositories that deploy on their own schedules, so a package would have to be
released and pulled before a fix reached anywhere. /healthz prints its version
so one site being behind the others is visible rather than something you find
out about.

The database is shared with the ticket site. Only three tables are this site's
own - intranet_group, intranet_member, intranet_rule - and it creates them
itself on boot.
"""
import datetime
import functools
import html as html_mod
import json
import os
import sys
import threading
import time
import traceback
import urllib.parse

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   session, url_for)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import titan_auth as auth        # noqa: E402  (a copy - see the note above)
import db                        # noqa: E402
import intranet_access           # noqa: E402

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "dev-only-not-for-azure"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

PASSCODE = os.environ.get("OFFICE_PASSCODE") or "titan"

# Kept only because the shared auth core refers to it. The intranet does not
# gate entry on a portal slug: anybody with a Titan account gets in, and what
# they SEE is intranet_access's job.
HR_SLUG = (os.environ.get("HR_SITE_SLUG") or "titan-hr").strip().lower()
SITE_SLUG = (os.environ.get("SITE_SLUG") or "").strip().lower()

SITE_DIR = os.environ.get("SITE_DIR") or os.path.join(HERE, "site")
PAGE = "index.html"
CONFIG = "config.json"
BUILD = datetime.datetime.now(datetime.timezone.utc)

_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".svg": "image/svg+xml", ".ico": "image/x-icon"}

CONFIG_START = "/* TITAN-CONFIG-START */"
CONFIG_END = "/* TITAN-CONFIG-END */"


def _html(s, code=200):
    return Response(s, status=code, mimetype="text/html",
                    headers={"Cache-Control": "no-store"})


def _brand_bit(which):
    """The ticket site draws these out of its generated brand.js. Here the
    helmet is simply a file, so the favicon is a path and there is no mark to
    inline."""
    return "/images/favicon.png" if which == "icon" else ""


_local = threading.local()


def conn():
    """One connection per thread, reopened if the pooler dropped it."""
    c = getattr(_local, "conn", None)
    if c is not None and not c.closed:
        try:
            c.execute("SELECT 1")
            return c
        except Exception:
            try:
                c.close()
            except Exception:
                pass
    _local.conn = db.connect()
    return _local.conn


# close-the-read-v1 ----------------------------------------------------------
# Connections are opened with autocommit off, which means the FIRST statement
# of any kind opens a transaction and it stays open until something commits or
# rolls back. Write paths do that. Read paths never did - and these connections
# live for the life of the thread, so a page that only read left a transaction
# open indefinitely, holding an AccessShareLock on everything it touched.
#
# What that cost, twice in one day: every ALTER TABLE in schema.sql waits for
# an ACCESS EXCLUSIVE lock, and an idle-in-transaction reader will not give up
# its share of it. Three of them were sitting on `jobs` when this was written -
# 15, 30 and 62 seconds and counting, one from the status page and two from the
# worker's poll - so the schema could not be applied at all, and the message
# blamed "another connection holding a lock", which was true and useless.
#
# Done here rather than by adding commit() to each read: there are dozens of
# reads and the next one written would forget. A request cannot leave a
# transaction open if the transaction is ended after every request, whatever
# the request did.
#
# Rolling back rather than committing is deliberate. Anything a view meant to
# keep, it committed. Anything still open at the end of a request is either a
# read - where rollback and commit are the same thing - or a write somebody
# forgot to commit, and that one should disappear loudly rather than be saved
# by a cleanup routine.
@app.teardown_request
def _end_transaction(exc=None):
    c = getattr(_local, "conn", None)
    if c is None or c.closed:
        return
    try:
        if c.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            c.rollback()
    except Exception:                      # a broken connection is conn()'s job
        pass


def store():
    s = getattr(_local, "store", None)
    if s is None and (os.environ.get("SUPABASE_URL") or "").strip():
        import storage
        s = _local.store = storage.from_env()
    return s


def protected(fn):
    """Nobody sees a page without being signed in, and once Microsoft sign-in
    is configured that means signed in *with Microsoft*.

    The second half is the part that was missing. `office` is true for a
    passcode session as well, and those cookies last thirty days, so everyone
    who was already logged in when sign-in was switched on would have carried
    on anonymously until their cookie expired - long enough that nobody would
    connect the two events. Requiring an email when auth is enabled ends those
    sessions at the next request.

    titan-sso-v1: and if there is no session here, try the two ways this person
    might already be signed in elsewhere before showing them a sign-in page.
    Cheapest first:

    1. This site's own cookie. Free, and the usual case.
    2. The shared ticket on .tetransports.com, if that shortcut is configured.
       Free, and it is what makes coming here from the portal instant.
    3. A silent round trip through Microsoft. About a second, nothing shown, and
       it needs no shared secret - so it is the one that has to be right.

    The old behaviour is the floor, not the ceiling: with sign-in off, or all
    three coming back empty, this does exactly what it did before.
    """
    @functools.wraps(fn)
    def go(*a, **kw):
        ok = session.get("office") and (session.get("email") or not auth.enabled())
        if ok:
            return fn(*a, **kw)

        # Everything identifying goes, and the one marker that must survive it
        # does. session.clear() is what ends a stale passcode session at the
        # next request, and it also wiped `sso_tried` - which is the cooldown
        # that stops a signed-out person becoming a redirect loop: no session,
        # silent attempt, login_required, clear the session, and round again on
        # the next click, forever. Carried across by hand rather than by not
        # clearing, because the clear is doing something else worth keeping.
        tried = session.get("sso_tried")
        session.clear()
        if tried:
            session["sso_tried"] = tried

        if auth.enabled():
            tk = auth.ticket_for(request)
            if tk:
                _adopt(tk)
                denied = _access_check()
                return denied if denied else fn(*a, **kw)

            if not _wants_json() and auth.should_try_silent(session, request):
                auth.note_silent_attempt(session)
                try:
                    return redirect(auth.begin(
                        session, request,
                        next_url=request.full_path.rstrip("?"), silent=True))
                except auth.AuthError as e:
                    app.logger.warning("silent sign-in could not start: %s", e)

        if _wants_json():
            return jsonify(error="signed out", login="/login"), 401
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    return go


def _adopt(person):
    """Establish a session for somebody Microsoft (or the shared ticket) has
    vouched for. The one place that writes an identity into the session, so
    there is no second path where a name could come from somewhere less
    trustworthy."""
    session["office"] = True
    session["email"] = person["email"]
    session["name"] = person.get("name") or person["email"]
    session.permanent = True
    auth.clear_silent_attempt(session)
    try:
        db.remember_person(conn(), session["email"], session["name"])
    except (Exception, SystemExit) as e:
        # Never worth failing a sign-in over: this is a nicety so a report can
        # show a name months later, not part of letting somebody in.
        #
        # SystemExit is named explicitly, which looks like belt and braces and
        # is not. db.url() raises SystemExit when DATABASE_URL is unset - right
        # at boot, where a loud failure beats a quiet hole, but SystemExit
        # inherits from BaseException, so a plain `except Exception` here lets
        # it through and kills the request. On the deployed site DATABASE_URL is
        # always set and the failure would be an ordinary psycopg error, so this
        # only bites on a desk - which is exactly where somebody is trying to
        # get sign-in working and least wants an unexplained crash.
        app.logger.warning("could not record who signed in: %s", e)


# ---------------------------------------------------------------------------
#  timecards-v1: /hr is a different site, wearing the same address
# ---------------------------------------------------------------------------
#
# Being allowed to review tickets and being allowed to see the payroll are not
# the same permission, and they must not be the same permission by accident.
# Everyone in the office reviews tickets. Almost none of them should be able to
# read what their colleagues are paid.
#
# So /hr asks about its OWN slug. Access is granted per person in the portal,
# the same table and the same tested code path the ticket site uses - not a new
# mechanism written in a hurry for the one area where a mistake is worst.
#
# Fails CLOSED, unlike the ticket site's check. There, an unset SITE_SLUG means
# "not turned on yet" and lets a signed-in person through, which is right for a
# system whose worst case is seeing a water ticket. Here the worst case is a
# colleague's wages, so an unconfigured slug means nobody except break-glass.
HR_SLUG = (os.environ.get("HR_SITE_SLUG") or "titan-hr").strip().lower()


def hr_only(fn):
    @functools.wraps(fn)
    @protected
    def go(*a, **kw):
        email = (session.get("email") or "").strip().lower()
        if not email:
            return _login_page("Payroll needs a Microsoft sign-in.")
        try:
            allowed = auth.may_use(conn(), email, HR_SLUG)
        except Exception as e:
            app.logger.error("could not check HR access: %s", e)
            return _login_page(
                "This site cannot reach the database that records who may see "
                "payroll, so it cannot let anyone in."), 503
        if not allowed:
            app.logger.warning("HR refused for %s", email)
            return _html(
                "<!doctype html><meta charset=utf-8><title>Not for you</title>"
                "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:560px;"
                "margin:14vh auto;padding:0 22px;color:#1f2430}a{color:#243090}"
                "</style><h1>This area is for payroll</h1>"
                "<p>You are signed in as <b>%s</b>, and that account has not "
                "been given access to the timesheets. This is separate from "
                "your access to the tickets, which is unaffected.</p>"
                "<p>If you should have it, ask whoever administers the portal "
                "to add you to <code>%s</code>.</p>"
                "<p><a href=\"/\">Back to tickets</a></p>"
                % (html_mod.escape(email), html_mod.escape(HR_SLUG))), 403
        return fn(*a, **kw)
    return go


def _access_check():
    """None if this person may use this site, or a response saying they may not.

    Asked here and not left to the portal. The portal hiding a tile is a
    courtesy; this is the control. A site that trusted the portal to have done
    the checking would be open to anyone in the tenant who typed its address,
    which is most of the company.

    Only enforced when SITE_SLUG is set, so this is inert until somebody turns
    it on deliberately - the same discipline as AUTH_CLIENT_ID. Deploying it
    without that setting cannot lock anybody out.
    """
    if not auth.SITE:
        return None
    email = session.get("email")
    if not email:
        return None
    try:
        if auth.may_use(conn(), email, auth.SITE):
            return None
    except Exception as e:
        # may_use fails closed on its own, so reaching here means something
        # worse - no connection at all. Say so rather than showing a bare
        # refusal that reads as "you are not allowed".
        app.logger.error("could not check access: %s", e)
        return _login_page(
            "This site cannot reach the database that records who may use it, "
            "so it cannot let anyone in. Nothing is wrong with your account."
        ), 503
    who = html_mod.escape(email)
    return _login_page(
        "You are signed in correctly as <b>%s</b>, but that account has not "
        "been given access to the ticket system. This is not a sign-in problem. "
        "Ask Serj to add you on the portal's access screen at "
        "<b>portal.tetransports.com</b> - it takes a minute and works straight "
        "away." % who), 403


def _wants_json():
    """Whether this is a fetch() from a page rather than a person navigating.

    A redirect answered to fetch() is followed silently and the caller gets the
    sign-in page's HTML where it expected JSON, which surfaces as a parse error
    with no hint that the session ran out. A 401 lets the page say so.
    """
    if request.headers.get("X-Requested-With") == "fetch":
        return True
    if request.method == "POST" and "application/json" in (request.content_type or ""):
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def _who():
    """The signed-in person, for anything that records who did it.

    who-did-what-v1: the one place that answers this question, so there is no
    second path where a name could come from somewhere less trustworthy. It
    reads the session, which is a signed cookie this server wrote when
    Microsoft vouched for them, and nothing else - in particular, never a field
    out of a request body.

    "office" is what everything before sign-in was, and what it still is if the
    passcode is being used. Honest: it means nobody knows which person.
    """
    return session.get("email") or "office"


# ---------------------------------------------------------------------------
#  Health and sign-in
# ---------------------------------------------------------------------------

def _login_page(err="", note=None):
    """who-did-what-v1: the Microsoft button when sign-in is configured, the
    old passcode box when it is not.

    Both are never offered at once, on purpose. A passcode sitting beside the
    button is a way back to being anonymous, and someone in a hurry will take
    it - which quietly undoes the entire point of the change.
    """
    if auth.enabled():
        nxt = request.args.get("next") or ""
        body = MS_BUTTON % (("?next=" + urllib.parse.quote(nxt)) if nxt else "")
        note = note or "Sign in with your Titan account."
    else:
        body = PASSCODE_FORM
        note = note or "Office use."
    # The way out, printed where somebody locked out would actually be
    # standing. A sign-in that cannot complete - a redirect URI not registered,
    # an expired secret - takes the passcode form with it, and knowing the
    # recovery exists is no use if it is only written in a file on a desktop.
    if err and auth.enabled():
        err += ('<div class=alt>If nobody can get in: remove the '
                '<b>AUTH_CLIENT_ID</b> app setting in Azure and the site goes '
                'back to the passcode within a restart. Nothing is lost.</div>')
    return LOGIN_HTML % {
        "note": note,
        "body": body,
        "err": ('<div class=err>%s</div>' % err) if err else "",
        "mark": _brand_bit("mark"),
        "icon": _brand_bit("icon"),
    }

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if auth.enabled():
            # The form is not served in this mode; a POST here is a stale tab
            # or somebody trying the old way.
            return _login_page("This site now uses Microsoft sign-in."), 400
        if request.form.get("passcode") == PASSCODE:
            session["office"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("home"))
        return _login_page("That passcode is not right.")
    return _login_page()


@app.get("/auth/start")
def auth_start():
    # Where they were heading, kept aside for the callback. Microsoft does not
    # carry query parameters of ours through the round trip, and it must be a
    # path on this site - "come back to wherever this says" is how an open
    # redirect gets built by accident.
    nxt = auth.safe_next(request.args.get("next"))
    session["oidc_next"] = nxt
    # Somebody clicking the button is a deliberate act, so an earlier failed
    # silent attempt must not be allowed to sit in the way of it.
    auth.clear_silent_attempt(session)
    try:
        return redirect(auth.begin(session, request, nxt, silent=False))
    except auth.AuthError as e:
        return _login_page(str(e)), 400


@app.get("/auth/callback")
def auth_callback():
    try:
        person = auth.complete(session, request, request.args)
    except auth.NeedsInteraction:
        # titan-sso-v1: expected, not a failure. A silent attempt found no
        # Microsoft session, which is simply what somebody arriving in the
        # morning looks like. Straight to the sign-in page with no error shown -
        # showing one would have the whole office reporting a broken site at
        # 7am.
        return _login_page()
    except auth.AuthError as e:
        return _login_page(str(e)), 400

    # Remembered so the report can show a name months later, including for
    # somebody whose account has since been closed. Inside _adopt, and never
    # worth failing a sign-in over.
    _adopt(person)

    denied = _access_check()
    if denied:
        return denied

    nxt = auth.safe_next(session.pop("oidc_next", None) or person.get("next"))
    r = redirect(nxt)
    # Mint the shared ticket here too, so somebody who came straight to the
    # tickets site is then recognised by the portal and every other system. No
    # site is the special one that grants identity; whichever they reach first
    # does it.
    return auth.set_ticket(r, person["email"], person["name"])


@app.get("/me.json")
@protected
def me_json():
    """Who the page is being shown to.

    Its own request rather than a value rendered into the page, because the
    review page is cached and shared between everybody who opens that batch -
    a name baked in would be whoever's browser happened to render it first.
    """
    email = session.get("email")
    return Response(
        json.dumps({"email": email, "name": session.get("name") or email}
                   if email else {}),
        mimetype="application/json", headers={"Cache-Control": "no-store"})


@app.get("/logout")
def logout():
    session.clear()
    # Signed out of this site only. Signing them out of Microsoft as well would
    # take Outlook and Teams with it, which is not what anyone means by "log out
    # of the tickets". The portal offers that as a second, plainly-labelled
    # option for a shared machine.
    #
    # titan-sso-v1: the shared ticket has to go too, or the next page load reads
    # it and signs them straight back in - which would look like a sign-out
    # button that does not work.
    r = app.make_response(_login_page(note="Signed out."))
    return auth.clear_ticket(r)


# ---------------------------------------------------------------------------
#  The review pages
# ---------------------------------------------------------------------------


# The Access screen wears the intranet's own colours rather than the ticket
# site's admin theme - it belongs to this site now, and importing a palette
# from another repository is exactly the coupling this split was for.
ACCESS_CSS = """
:root{--navy:#1e2a78;--red:#d21f2c;--cyan:#2bb0e8;--black:#0f1115;
  --card:#262a33;--card-2:#2e333e;--line:#3a3f4b;--page:#1b1e24;
  --ink:#e8eaef;--mut:#a6acb8;--good:#3ecf8e;--goodbg:#123a2c;
  --bad:#ff8080;--badbg:#3d1b22;--info:#7fd2f5;--accent:#2bb0e8}
*{box-sizing:border-box}
body{font:15px/1.6 Inter,"Segoe UI",system-ui,sans-serif;background:var(--page);
  color:var(--ink);margin:0}
a{color:var(--info);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3{margin:0 0 .4em;line-height:1.2;font-family:"Barlow Condensed",
  "Arial Narrow",sans-serif;text-transform:uppercase;letter-spacing:.6px}
.bar{background:rgba(27,30,36,.98);border-bottom:4px solid var(--red);
  padding:11px 22px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.bar .plate{width:34px;height:34px;background:#fff;border-radius:9px;
  display:grid;place-items:center}
.bar .plate i{display:block;height:24px;aspect-ratio:110/160;
  background:url(/images/titan-energy-helmet.png) center/contain no-repeat}
.bar .brand b{font-family:"Barlow Condensed",sans-serif;font-size:19px;
  text-transform:uppercase;letter-spacing:.6px}
.bar .brand span{display:block;font-size:11.5px;color:var(--mut)}
.bar .sp{flex:1}
.bar .back,.bar .hr-who{font-size:13px;color:var(--mut)}
.btn{display:inline-block;background:var(--red);color:#fff;border:0;
  border-radius:8px;padding:9px 16px;font:600 13.5px/1 inherit;cursor:pointer}
.btn:hover{filter:brightness(1.09)}
.btn.small{padding:7px 12px;font-size:12.5px}
.btn.danger{background:transparent;border:1px solid #5c2630;color:var(--bad)}
input,textarea,select{background:var(--black);color:var(--ink);
  border:1px solid var(--line);border-radius:8px;padding:9px 11px;
  font:14px/1.4 inherit;width:100%}
input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
"""


# intranet-permissions-v1: the page is assembled per person.
#
# The configuration used to sit in the HTML, which meant hiding a card in
# JavaScript was a curtain and not a lock - View Source and there were all 149
# document names and every folder path. Now config.json is filtered here and
# written into the page between two markers, so a person's copy of the page
# holds only what that person may see.
#
# The file is parsed once and cached against its mtime: it is the same 19 KB
# for every request and re-reading it per person is work for nothing. Filtering
# copies rather than mutating, so the cached parse is never touched.
_CFG_CACHE = {"mtime": None, "data": None}
_CFG_LOCK = threading.Lock()

CONFIG_START = "/* TITAN-CONFIG-START */"
CONFIG_END = "/* TITAN-CONFIG-END */"


def site_config():
    """config.json, parsed. Re-read when the file changes on disk."""
    path = os.path.join(SITE_DIR, CONFIG)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _CFG_LOCK:
        if _CFG_CACHE["mtime"] != mtime:
            with open(path, encoding="utf-8") as f:
                _CFG_CACHE["data"] = json.load(f)
            _CFG_CACHE["mtime"] = mtime
        return _CFG_CACHE["data"]


def _who_and_groups():
    email = (session.get("email") or "").strip().lower()
    try:
        groups = intranet_access.groups_for(conn(), email)
    except Exception:
        groups = set()
    return email, groups


@app.get("/")
@protected
def intranet_home():
    path = os.path.join(SITE_DIR, PAGE)
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError:
        app.logger.error("page not found at %s", path)
        return _html(
            "<!doctype html><meta charset=utf-8><title>Not deployed</title>"
            "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:560px;"
            "margin:14vh auto;padding:0 22px}code{background:#eee;padding:2px "
            "5px}</style><h1>The intranet page is not on the server</h1>"
            "<p>Expected it at <code>%s</code>. Run <b>Publish Intranet.cmd</b> "
            "and deploy again.</p>" % html_mod.escape(path)), 404
    cfg = site_config()
    if cfg is None:
        app.logger.error("config.json missing at %s", SITE_DIR)
        return _html(
            "<!doctype html><meta charset=utf-8><title>Not deployed</title>"
            "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:560px;"
            "margin:14vh auto;padding:0 22px}code{background:#eee;padding:2px 5px}"
            "</style><h1>The intranet has no configuration</h1><p>Expected "
            "<code>config.json</code> next to the page. Run <b>Publish "
            "Intranet.cmd</b> and deploy again.</p>"), 404

    email, groups = _who_and_groups()
    filtered, hidden = intranet_access.filter_config(
        cfg, intranet_access.all_rules(conn()), groups,
        admin=intranet_access.is_admin(email, groups))
    filtered = dict(filtered)
    filtered["viewer"] = {
        "email": email,
        "groups": sorted(groups),
        "admin": intranet_access.is_admin(email, groups),
    }

    page = body.decode("utf-8")
    a, b = page.find(CONFIG_START), page.find(CONFIG_END)
    if a == -1 or b == -1:
        app.logger.error("the page has no config markers")
        abort(500)
    page = (page[:a + len(CONFIG_START)]
            # </script> inside a string would close this block early, and the
            # rest of the page would be parsed as HTML. json.dumps does not
            # escape it, so it is done here.
            + "\nvar TITAN = "
            + json.dumps(filtered, ensure_ascii=False).replace("</", "<\\/")
            + ";\n"
            + page[b:])

    if sum(hidden.values()):
        app.logger.info("intranet for %s: hid %s", email or "?", hidden)

    # no-store, and Vary on Cookie: this page is different for every person now,
    # so a shared cache handing one person's copy to another would be a leak
    # rather than a stale page.
    return Response(page, mimetype="text/html",
                    headers={"Cache-Control": "no-store, private",
                             "Vary": "Cookie"})


@app.get("/images/<name>")
@protected
def image(name):
    """<name> and not <path:name>, so a slash cannot walk out of the folder."""
    ext = os.path.splitext(name)[1].lower()
    if ext not in _IMAGE_TYPES or "/" in name or ".." in name:
        abort(404)
    try:
        with open(os.path.join(SITE_DIR, "images", name), "rb") as f:
            body = f.read()
    except OSError:
        abort(404)
    return Response(body, mimetype=_IMAGE_TYPES[ext],
                    headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
#  The Access screen
# ---------------------------------------------------------------------------

def admin_only(fn):
    """Signed in, on the intranet, and an administrator."""
    @functools.wraps(fn)
    @protected
    def go(*a, **kw):
        email, groups = _who_and_groups()
        if not intranet_access.is_admin(email, groups):
            return _html(
                "<!doctype html><meta charset=utf-8><title>Not for you</title>"
                "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:560px;"
                "margin:14vh auto;padding:0 22px;color:#1f2430}a{color:#243090}"
                "</style><h1>This screen is for administrators</h1>"
                "<p>You are signed in as <b>%s</b>. Ask whoever administers the "
                "intranet to put you in the <code>admins</code> group, or to add "
                "you to <code>PORTAL_ADMINS</code>.</p>"
                "<p><a href=\"/\">Back to the intranet</a></p>"
                % html_mod.escape(email or "nobody")), 403
        return fn(*a, **kw)
    return go


def _ticks(key, groups, chosen):
    """One group tick box per group, for one item."""
    out = []
    for g in groups:
        out.append(
            '<label class=tick><input type=checkbox name="rule:%s" value="%s"%s>'
            '<span>%s</span></label>' % (
                html_mod.escape(key), html_mod.escape(g["name"]),
                " checked" if g["name"] in chosen else "",
                html_mod.escape(g["label"])))
    return "".join(out)


@app.get("/access")
@admin_only
def access_screen():
    c = conn()
    intranet_access.ensure(c)
    cfg = site_config() or {}
    groups = intranet_access.all_groups(c)
    rules = intranet_access.all_rules(c)
    members = intranet_access.all_members(c)

    # -- people -----------------------------------------------------------
    people = []
    for email in sorted(members):
        mine = members[email]
        people.append(
            '<form method=post action="/access/person" class=row>'
            '<input type=hidden name=email value="%s">'
            '<span class=who>%s</span><span class=ticks>%s</span>'
            '<button class="btn small">Save</button>'
            '<button class="btn small danger" formaction="/access/person/remove"'
            ' name=email value="%s">Remove</button></form>' % (
                html_mod.escape(email), html_mod.escape(email),
                "".join('<label class=tick><input type=checkbox name=groups '
                        'value="%s"%s><span>%s</span></label>' % (
                            html_mod.escape(g["name"]),
                            " checked" if g["name"] in mine else "",
                            html_mod.escape(g["label"])) for g in groups),
                html_mod.escape(email)))

    # -- what each item shows ---------------------------------------------
    sections, last_kind = [], None
    for item in intranet_access.inventory(cfg):
        if item["kind"] != last_kind:
            sections.append('<h3 class=kind>%s</h3>'
                            % html_mod.escape(item["kind"].title() + "s"))
            last_kind = item["kind"]
        keys = [item["key"]] + [ch["key"] for ch in item["children"]]
        open_now = any(k in rules for k in keys)
        kids = ""
        if item["children"]:
            kids = (
                '<details class=kids%s><summary>%d document%s</summary>%s</details>'
                % (" open" if open_now else "", len(item["children"]),
                   "" if len(item["children"]) == 1 else "s",
                   "".join(
                       '<div class="row kid"><span class=who>%s</span>'
                       '<span class=ticks>%s</span>%s</div>' % (
                           html_mod.escape(ch["label"]),
                           _ticks(ch["key"], groups, rules.get(ch["key"], set())),
                           '<span class=state>%s</span>' % (
                               "restricted" if ch["key"] in rules else "everyone"))
                       for ch in item["children"])))
        sections.append(
            '<form method=post action="/access/rules" class=item>'
            '<input type=hidden name=keys value="%s">'
            '<div class=row><b class=who>%s</b><span class=ticks>%s</span>'
            '<span class=state>%s</span></div>%s'
            '<div class=save><button class="btn small">Save this section</button>'
            '</div></form>' % (
                html_mod.escape("\n".join(keys)),
                html_mod.escape(item["label"]),
                _ticks(item["key"], groups, rules.get(item["key"], set())),
                "restricted" if item["key"] in rules else "everyone",
                kids))

    return _html(ACCESS_HTML % {
        "css": ACCESS_CSS,
        "icon": _brand_bit("icon"),
        "who": html_mod.escape(session.get("email") or ""),
        "people": "".join(people) or
                  '<p class=muted>Nobody has been given a group yet. Everyone '
                  'signing in sees whatever is not restricted.</p>',
        "groups": "".join(
            '<form method=post action="/access/group/remove" class=chip>%s'
            '<input type=hidden name=name value="%s">'
            '%s</form>' % (
                html_mod.escape(g["label"]), html_mod.escape(g["name"]),
                "" if g["name"] == intranet_access.ADMIN_GROUP
                else '<button title="Delete this group">&times;</button>')
            for g in groups),
        "sections": "".join(sections),
        "notice": ('<p class="note ok">%s</p>' % html_mod.escape(request.args["ok"]))
                  if request.args.get("ok") else
                  ('<p class="note err">%s</p>' % html_mod.escape(request.args["err"]))
                  if request.args.get("err") else "",
    })


@app.post("/access/person")
@admin_only
def access_person():
    c = conn()
    try:
        intranet_access.set_member_groups(
            c, request.form.get("email"), request.form.getlist("groups"),
            by=session.get("email"))
    except ValueError as e:
        return redirect(url_for("access_screen", err=str(e)))
    return redirect(url_for("access_screen",
                            ok="Saved %s." % request.form.get("email")))


@app.post("/access/person/remove")
@admin_only
def access_person_remove():
    intranet_access.drop_member(conn(), request.form.get("email"))
    return redirect(url_for("access_screen",
                            ok="Removed %s from every group." % request.form.get("email")))


@app.post("/access/people/add")
@admin_only
def access_people_add():
    c = conn()
    emails = intranet_access.emails_from(request.form.get("emails"))
    if not emails:
        return redirect(url_for("access_screen",
                                err="No email addresses in that."))
    groups = request.form.getlist("groups")
    for e in emails:
        intranet_access.set_member_groups(c, e, groups, by=session.get("email"))
    return redirect(url_for("access_screen",
                            ok="Added %d %s." % (len(emails),
                                                 "person" if len(emails) == 1
                                                 else "people")))


@app.post("/access/rules")
@admin_only
def access_rules():
    """Save one section and its documents.

    The form carries the keys it is responsible for, and every one of them is
    rewritten - including the ones with no box ticked, which is how a rule gets
    removed. Saving only the ticked ones would make "everyone" unreachable once
    anything had ever been restricted.
    """
    c = conn()
    keys = [k for k in (request.form.get("keys") or "").split("\n") if k.strip()]
    for key in keys:
        intranet_access.set_rule(c, key, request.form.getlist("rule:" + key))
    return redirect(url_for("access_screen", ok="Saved."))


@app.post("/access/group")
@admin_only
def access_group_add():
    try:
        intranet_access.add_group(conn(), request.form.get("name"),
                                  request.form.get("label"))
    except ValueError as e:
        return redirect(url_for("access_screen", err=str(e)))
    return redirect(url_for("access_screen", ok="Group added."))


@app.post("/access/group/remove")
@admin_only
def access_group_remove():
    try:
        intranet_access.drop_group(conn(), request.form.get("name"))
    except ValueError as e:
        return redirect(url_for("access_screen", err=str(e)))
    return redirect(url_for("access_screen",
                            ok="Group deleted, and every rule that used it."))


ACCESS_HTML = """<!doctype html><meta charset=utf-8>
<title>Intranet access</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=icon href="%(icon)s">
<style>
%(css)s
 .wrap{max-width:1100px;margin:0 auto;padding:20px 22px 70px}
 h2{margin:34px 0 4px;font-size:18px}
 h3.kind{margin:22px 0 6px;font-size:12px;text-transform:uppercase;
   letter-spacing:.14em;color:var(--mut)}
 .lede{color:var(--mut);font-size:13.5px;margin:0 0 6px;max-width:74ch}
 .note{border-radius:9px;padding:10px 14px;margin:14px 0;font-size:14px}
 .note.ok{background:var(--goodbg);color:#b6f0d6}
 .note.err{background:var(--badbg);color:#ffc4c4}
 .item{background:var(--card);border:1px solid var(--line);border-radius:11px;
   padding:10px 14px;margin:0 0 9px}
 .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
   background:var(--card);border:1px solid var(--line);border-radius:10px;
   padding:8px 12px;margin:0 0 7px}
 .item>.row{background:none;border:0;padding:0;margin:0}
 .who{flex:1;min-width:220px;font-size:14px}
 .ticks{display:flex;gap:10px;flex-wrap:wrap}
 .tick{display:flex;align-items:center;gap:5px;font-size:12.5px;color:var(--mut);
   white-space:nowrap;cursor:pointer}
 .tick input{accent-color:var(--accent);cursor:pointer}
 .state{font-size:11px;color:var(--mut);min-width:66px;text-align:right}
 .kids{margin:8px 0 0;border-top:1px solid var(--line);padding-top:8px}
 .kids summary{cursor:pointer;color:var(--info);font-size:12.5px;padding:2px 0}
 .kid{background:var(--card-2);margin-top:6px}
 .kid .who{font-size:13px;color:var(--mut)}
 .save{margin-top:9px}
 .chip{display:inline-flex;align-items:center;gap:6px;background:var(--card-2);
   border:1px solid var(--line);border-radius:20px;padding:4px 10px;
   font-size:12.5px;margin:0 6px 6px 0}
 .chip button{background:none;border:0;color:var(--mut);cursor:pointer;font-size:14px}
 .chip button:hover{color:var(--bad)}
 .addbox{background:var(--card);border:1px solid var(--line);border-radius:11px;
   padding:14px 16px;margin:10px 0 0}
 textarea{min-height:64px}
 .muted{color:var(--mut);font-size:13.5px}
</style>
<div class=bar>
  <span class=plate><i></i></span>
  <span class=brand><b>Intranet access</b><span>Titan Enterprises</span></span>
  <span class=sp></span>
  <span class=hr-who>%(who)s</span>
  <a class=back href="/">&larr; Back to the intranet</a>
</div>
<div class=wrap>
  %(notice)s

  <h2>Groups</h2>
  <p class=lede>People go in groups; groups are what sections are opened to.</p>
  <div>%(groups)s</div>
  <form method=post action="/access/group" class=addbox>
    <div class=row style="background:none;border:0;padding:0">
      <input name=label placeholder="Yard Managers" style="max-width:240px">
      <input name=name placeholder="yard-managers" style="max-width:240px">
      <button class="btn small">Add group</button>
    </div>
    <p class=muted style="margin:8px 0 0">The second box is the short name used
    in the database. Leave it and it will be made from the first.</p>
  </form>

  <h2>People</h2>
  <p class=lede>Anybody signing in with a Titan account gets the intranet.
  Groups decide how much of it. Somebody who is in no group still sees
  everything that has not been restricted.</p>
  %(people)s
  <form method=post action="/access/people/add" class=addbox>
    <textarea name=emails placeholder="paste addresses, one per line or comma separated"></textarea>
    <div class=row style="background:none;border:0;padding:8px 0 0">
      <span class=muted>Put them in:</span>
      <span class=ticks id=addgroups></span>
      <button class="btn small">Add people</button>
    </div>
  </form>

  <h2>What each section shows</h2>
  <p class=lede>Tick nothing and a section is open to everyone &mdash; that is
  the default, and it is why a new starter is useful on day one. Tick a group
  and only that group sees it. A section that is shut hides its documents too,
  so to give everybody a few rows out of a restricted area, leave the section
  open and restrict the rows instead.</p>
  %(sections)s
</div>
<script>
/* The add-people form needs the same group boxes as the rows above it, and
   building them here rather than server-side keeps one copy of the list. */
(function(){
  var first = document.querySelector('form[action="/access/person"] .ticks');
  var into  = document.getElementById('addgroups');
  if (first && into){
    into.innerHTML = first.innerHTML.replace(/ checked/g, '');
  } else if (into) {
    var boxes = document.querySelectorAll('.chip');
    var out = '';
    for (var i = 0; i < boxes.length; i++){
      var name = boxes[i].querySelector('input[name=name]').value;
      out += '<label class=tick><input type=checkbox name=groups value="' +
             name + '"><span>' + boxes[i].childNodes[0].nodeValue.trim() +
             '</span></label>';
    }
    into.innerHTML = out;
  }
})();
</script>
"""


#  orientation-print-v1: batch printing the new-hire packets
# ---------------------------------------------------------------------------
# One person runs orientation, and used to open nine PDFs out of SharePoint and
# print each one, per new hire. The intranet page has a popup that lists the
# folder and posts a selection here; this merges it into a single PDF so the
# browser opens one print dialog.
#
# Same access group as payroll by default. Orientation packets are HR material
# and it is the same person, so ORIENTATION_SITE_SLUG only needs setting if
# that ever stops being true.

ORIENTATION_SLUG = (os.environ.get("ORIENTATION_SITE_SLUG")
                    or HR_SLUG).strip().lower()

# ORIENTATION_USERS is the way in that does not need the portal.
#
# The portal owns `portal_sites` and `portal_access`, in its own schema. Until
# the portal is deployed those tables do not exist, so auth.may_use() throws,
# fails closed as it is designed to, and there is nothing anywhere that can
# grant anybody access - the feature is unusable by everyone except whoever is
# in PORTAL_ADMINS, with no way to fix it from a screen.
#
# So: a plain comma-separated list in an app setting. Additive, never
# subtractive - being on it grants access, and not being on it just falls
# through to the portal check that will start working when the portal lands.
# Nobody who has access today loses it then.
ORIENTATION_USERS = [e.strip().lower()
                     for e in (os.environ.get("ORIENTATION_USERS") or "").split(",")
                     if e.strip()]


def orientation_only(fn):
    """Signed in with Microsoft, and on one of the two lists.

    Answers JSON rather than a sign-in page: every caller is fetch() from the
    intranet popup, and an HTML login form arriving where a JSON body was
    expected shows up as an unexplained failure.
    """
    @functools.wraps(fn)
    @protected
    def go(*a, **kw):
        email = (session.get("email") or "").strip().lower()
        if not email:
            return jsonify(ok=False, error="Sign in with Microsoft first."), 401

        if email in ORIENTATION_USERS:
            return fn(*a, **kw)

        # Not on the list: ask the portal, if there is one. A missing table is
        # the ordinary answer here rather than a fault, so it is not logged as
        # an error and does not become a 503 - it just means "no".
        try:
            allowed = auth.may_use(conn(), email, ORIENTATION_SLUG)
        except Exception as e:
            app.logger.info("no portal access tables to check (%s)", e)
            allowed = False

        if not allowed:
            app.logger.warning("orientation refused for %s", email)
            return jsonify(ok=False, error=(
                "%s has not been given access to the orientation packets. Add "
                "that address to the ORIENTATION_USERS setting on this app, or "
                "to %s in the portal once it is running."
                % (email, ORIENTATION_SLUG))), 403
        return fn(*a, **kw)
    return go


# One Library per process, and a short-lived listing cache.
#
# from_env() used to run on every request, and a fresh Library means a fresh
# OAuth token fetch, a site lookup and a drives lookup before the folder is
# even asked for - four sequential round trips to Graph to answer "what is in
# this folder". Held across requests, the token and the resolved drive id are
# reused and it becomes one.
#
_ORIENT = {"lib": None}
_ORIENT_LOCK = threading.Lock()


def _orientation_lib():
    import orientation
    with _ORIENT_LOCK:
        lib = _ORIENT.get("lib")
        if lib is None:
            lib = orientation.from_env()      # raises if unconfigured; not cached
            _ORIENT["lib"] = lib
        return lib


@app.get("/api/orientation")
@orientation_only
def orientation_list():
    """The company folders, and the files in one of them.

    Read fresh every time. The popup calls this on open precisely so that a
    packet replaced ten minutes ago is the one that prints.
    """
    import orientation
    try:
        lib = _orientation_lib()
        return jsonify(orientation.listing(lib, request.args.get("folder") or ""))
    except orientation.NotConfigured as e:
        return jsonify(ok=False, error=str(e)), 501
    except orientation.OrientationError as e:
        return jsonify(ok=False, error=str(e)), 502
    except Exception as e:
        app.logger.exception("orientation listing failed")
        return jsonify(ok=False, error="Could not read the orientation folder: "
                       "%s" % str(e)[:200]), 500


@app.post("/api/print-packets")
@orientation_only
def orientation_print():
    """The chosen packets, merged into one PDF.

    Returns the PDF as the body on success and JSON on failure, because that is
    what the page checks: anything that is not application/pdf makes it fall
    back to showing the files as individual links.
    """
    import orientation
    body = request.get_json(silent=True) or {}
    info = {}
    try:
        lib = _orientation_lib()
        # duplex defaults to on: these are printed front and back, and the
        # padding is what stops one packet's page 1 landing on the back of the
        # previous packet's last sheet.
        pdf = orientation.build(lib,
                                body.get("folder") or "",
                                body.get("packets") or [],
                                body.get("copies") or 1,
                                duplex=body.get("duplex", True) is not False,
                                info=info)
    except orientation.NotConfigured as e:
        return jsonify(ok=False, error=str(e)), 501
    except orientation.OrientationError as e:
        return jsonify(ok=False, error=str(e)), 502
    except Exception as e:
        app.logger.exception("orientation merge failed")
        return jsonify(ok=False, error="Could not build the packet: %s"
                       % str(e)[:200]), 500

    app.logger.info("orientation: %d packets, %s, %d copies, %d pages "
                    "(%d blank), %.1f MB",
                    len(body.get("packets") or []), body.get("folder") or "?",
                    int(body.get("copies") or 1), info.get("pages") or 0,
                    info.get("blanks") or 0, len(pdf) / 1048576.0)
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": 'inline; filename="orientation-packets.pdf"',
        "Cache-Control": "no-store",
        # Read by the popup so it can explain the blank sheets.
        "X-Packet-Pages": str(info.get("pages") or 0),
        "X-Packet-Blanks": str(info.get("blanks") or 0),
        "Access-Control-Expose-Headers": "X-Packet-Pages, X-Packet-Blanks",
    })


# ---------------------------------------------------------------------------
#  Odds and ends
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    """Open to the internet, so it says whether things work and nothing else.

    The auth version is here because titan_auth.py is COPIED into every Titan
    site: one site being a fix behind the others is otherwise invisible.
    """
    ok, detail = True, {}
    try:
        cfg = site_config()
        detail["config"] = "ok" if cfg else "missing"
        ok = ok and bool(cfg)
    except Exception as e:
        ok, detail["config"] = False, str(e)[:120]
    try:
        with conn().cursor() as cur:
            cur.execute("SELECT 1")
        detail["database"] = "ok"
    except Exception as e:
        ok, detail["database"] = False, str(e)[:120]
    detail["auth"] = getattr(auth, "VERSION", "unknown")
    detail["build"] = BUILD.isoformat(timespec="seconds")
    return jsonify(ok=ok, **detail), (200 if ok else 503)


@app.before_request
def _boot():
    """Make this site's three tables once per worker.

    Its own tables, not the ticket site's schema, so a change here never takes
    a lock on a table reviewers are filing tickets into.
    """
    if not BOOTED["done"]:
        if time.time() - BOOTED["last"] > 30:
            BOOTED["last"] = time.time()
            try:
                intranet_access.ensure(conn())
                BOOTED["done"] = True
            except Exception as e:
                app.logger.error("could not prepare the access tables: %s", e)


BOOTED = {"done": False, "last": 0.0}


@app.errorhandler(Exception)
def _unhandled(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    ref = datetime.datetime.now().strftime("%H%M%S")
    app.logger.error("unhandled error ref=%s on %s\n%s",
                     ref, request.path, traceback.format_exc())
    if _wants_json():
        return jsonify(ok=False, error=str(e)[:200], ref=ref), 500
    return _html(
        "<!doctype html><meta charset=utf-8><title>Something broke</title>"
        "<style>body{font:15px/1.6 system-ui,sans-serif;max-width:560px;"
        "margin:14vh auto;padding:0 22px}code{background:#eee;padding:2px 5px}"
        "</style><h1>Something broke</h1><p>%s</p><p>Reference <code>%s</code> "
        "&mdash; quote it and the log can be found.</p>"
        % (html_mod.escape(str(e)[:200]), ref), 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8001)), debug=False)
