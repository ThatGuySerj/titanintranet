"""The Titan Enterprises intranet.

    gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app

Its own site, its own repository, its own Azure Web App. It was part of the
ticket app for a fortnight and that was the wrong shape: one process meant one
restart, so renaming a link on the noticeboard took the site people file
tickets in down with it.

What it serves:

    /                 the intranet, built per person
    /images/<name>    the logos
    /fileplan         the proposed filing structure, walkable
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

import psycopg                   # noqa: E402  (for _end_transaction)
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


# ---------------------------------------------------------------------------
#  The sign-in page
# ---------------------------------------------------------------------------
# Lifted from the ticket site along with _login_page, so the two look the same
# to somebody who uses both. `mark` resolves to nothing here, because the
# helmet on this site is a file rather than something inlined out of brand.js -
# the page renders without it rather than failing, which is what the ticket
# site's own comment says to do.

LOGIN_HTML = """<!doctype html><meta charset=utf-8>
<title>Titan Enterprises Intranet</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=icon href="%(icon)s">
<style>
 :root{--navy:#243090;--navy-dark:#1A2470;--navy-light:#3949B8;
       --accent:#00AAE6;--red:#E41824;
       --ink:#1C2230;--ink-soft:#4a5568;--line:#cbd5e1}
 *{box-sizing:border-box}
 body{font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;
      min-height:100vh;display:grid;place-items:center;padding:24px;
      color:var(--ink);
      background:radial-gradient(120%% 90%% at 50%% 0%%,var(--navy) 0%%,
                 var(--navy-dark) 55%%,#0f1547 100%%)}
 .wrap{width:100%%;max-width:380px;text-align:center}
 /* The helmet sits on white, the way it does on the tracker header - the
    artwork has dark outlines and disappears against navy. */
 .plate{width:104px;height:104px;margin:0 auto 22px;background:#fff;
        border-radius:22px;display:grid;place-items:center;
        box-shadow:0 10px 30px rgba(0,0,0,.28)}
 .helm{width:52px;aspect-ratio:215/312;
       background:url("%(mark)s") center/contain no-repeat}
 .card{background:#fff;border-radius:18px;padding:30px 28px 26px;
       box-shadow:0 18px 44px rgba(0,0,0,.30);text-align:left}
 h1{font-size:20px;margin:0 0 5px;color:var(--navy);letter-spacing:-.01em}
 .sub{color:var(--ink-soft);margin:0 0 22px;font-size:13.5px}
 input{width:100%%;padding:12px 13px;border-radius:11px;border:1px solid var(--line);
       background:#fff;color:var(--ink);font:inherit;font-size:15px}
 input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px #e8eaf8}
 button,.ms{width:100%%;margin-top:12px;padding:13px;border:0;border-radius:11px;
        background:var(--navy);color:#fff;font:inherit;font-size:15px;
        font-weight:600;cursor:pointer;display:block;text-align:center;
        text-decoration:none}
 button:hover,.ms:hover{background:var(--navy-light,#3949B8)}
 .ms{display:flex;align-items:center;justify-content:center;gap:10px}
 .ms svg{flex:none}
 .err{color:var(--red);font-size:13px;margin-top:14px;line-height:1.45;
      background:#fee2e2;border-radius:9px;padding:10px 12px}
 .alt{color:var(--ink-soft);font-size:12px;margin:12px 0 0;line-height:1.5}
 .foot{color:#aab4e8;font-size:11.5px;margin:18px 0 0;letter-spacing:.03em;
       text-transform:uppercase}
</style>
<div class=wrap>
 <div class=plate><div class=helm></div></div>
 <div class=card>
  <h1>Titan Enterprises Intranet</h1>
  <p class=sub>%(note)s</p>
  %(body)s
  %(err)s
 </div>
 <p class=foot>Titan Enterprises</p>
</div>"""

# Microsoft's four squares, inline: the button is asking people to trust it
# with a company password, and a broken image on that button is exactly the
# thing that makes someone hesitate. No network fetch, nothing to break.
MS_MARK = ('<svg width=17 height=17 viewBox="0 0 23 23" aria-hidden=true>'
           '<path fill="#f35325" d="M1 1h10v10H1z"/>'
           '<path fill="#81bc06" d="M12 1h10v10H12z"/>'
           '<path fill="#05a6f0" d="M1 12h10v10H1z"/>'
           '<path fill="#ffba08" d="M12 12h10v10H12z"/></svg>')

MS_BUTTON = ('<a class=ms href="/auth/start%s">' + MS_MARK +
             '<span>Sign in with Microsoft</span></a>')

PASSCODE_FORM = """<form method=post>
 <input type=password name=passcode placeholder="Passcode" autofocus>
 <button>Sign in</button>
</form>"""



def _brand_bit(which):
    """The ticket site lifts these out of its generated brand.js. Here they are
    simply files, so they are paths - and the sign-in page gets a helmet rather
    than an empty white plate."""
    return ("/images/favicon.png" if which == "icon"
            else "/images/titan-energy-helmet.png")


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
/* The Access screen wears the intranet's own colours and type. It belongs to
   this site, and a settings page that looks like a different product makes
   people wonder whether they are still in the right place. */
:root{
  --navy:#1e2a78; --navy-dark:#141c52;
  --red:#d21f2c;  --red-dark:#a91723;
  --cyan:#2bb0e8; --cyan-light:#7fd2f5;
  --green:#3ecf8e; --amber:#f0b64b;
  --black:#0f1115; --steel:#c9ced8;
  --surface:#1b1e24; --card:#262a33; --card-2:#2e333e;
  --line:#3a3f4b;
  --ink:#e8eaef; --mut:#a6acb8; --dim:#7d848f;
  --bad:#ff8080; --badbg:#3d1b22; --goodbg:#123a2c;
  --font-display:"Barlow Condensed","Arial Narrow","Segoe UI",sans-serif;
  --font-body:"Inter","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --shadow:0 3px 10px rgba(0,0,0,.35);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font-body);background:var(--surface);color:var(--ink);
  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--cyan);text-decoration:none}
a:hover{color:var(--cyan-light)}
h1,h2,h3{font-family:var(--font-display);text-transform:uppercase;
  letter-spacing:.6px;line-height:1.1}
button,input,select,textarea{font-family:inherit}
:focus-visible{outline:2px solid var(--cyan);outline-offset:2px;border-radius:4px}

/* ---- masthead: the same one the intranet has ---- */
.bar{position:sticky;top:0;z-index:50;display:flex;align-items:center;gap:20px;
  padding:12px 26px;background:rgba(27,30,36,.98);backdrop-filter:blur(8px);
  border-bottom:4px solid var(--red);box-shadow:var(--shadow);flex-wrap:wrap}
.bar .logo{height:38px;width:auto;background:#fff;padding:5px 11px;border-radius:8px}
.bar .divider{width:1px;height:34px;background:var(--line)}
.bar .kicker{display:block;font-family:var(--font-display);font-size:.7rem;
  letter-spacing:.22em;text-transform:uppercase;color:var(--cyan);font-weight:600}
.bar .name{display:block;font-family:var(--font-display);font-size:1.35rem;
  font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#fff}
.bar .sp{flex:1}
.bar .who{font-size:12.5px;color:var(--mut);display:flex;align-items:center;gap:8px;
  border:1px solid var(--line);border-radius:999px;padding:5px 13px 5px 6px;
  background:#15181d}
.bar .who .av{width:26px;height:26px;border-radius:50%;display:grid;
  place-items:center;font:700 10px/1 var(--font-body);color:#fff;
  background:linear-gradient(135deg,var(--navy),var(--cyan))}
.bar .back{font-size:13px;font-weight:600;white-space:nowrap}

.wrap{max-width:1120px;margin:0 auto;padding:0 22px 80px}

/* ---- page head ---- */
.head{padding:26px 0 22px;display:flex;align-items:flex-end;gap:26px;flex-wrap:wrap}
.head h1{font-size:clamp(1.6rem,2.6vw,2.2rem);color:#fff;font-weight:700}
.head .rule{width:78px;height:4px;border-radius:2px;margin:12px 0;
  background:linear-gradient(90deg,var(--red),var(--cyan))}
.head p{color:var(--mut);font-size:14px;max-width:66ch}
.head .tally{margin-left:auto;display:flex;gap:26px;flex:none}
.head .tally div{text-align:right}
.head .tally b{display:block;font-family:var(--font-display);font-size:1.7rem;
  color:#fff;font-weight:700;line-height:1}
.head .tally span{font-size:11px;color:var(--dim);text-transform:uppercase;
  letter-spacing:.12em}

/* ---- section bands ---- */
.band{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin:34px 0 0;
  padding-bottom:10px;border-bottom:2px solid var(--red)}
.band h2{font-size:1.25rem;color:#fff;font-weight:700}
.band .sub{font-size:12.5px;color:var(--dim);max-width:58ch}
.band .tools{margin-left:auto;display:flex;align-items:center;gap:10px}

.note{border-radius:9px;padding:11px 15px;margin:16px 0 0;font-size:14px;
  border:1px solid transparent}
.note.ok{background:var(--goodbg);border-color:#1e5c45;color:#b6f0d6}
.note.err{background:var(--badbg);border-color:#5c2630;color:#ffc4c4}

/* ---- buttons ---- */
.btn{display:inline-block;background:var(--red);color:#fff;border:0;
  border-radius:8px;padding:9px 17px;font:700 12.5px/1 var(--font-body);
  letter-spacing:.03em;cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--red-dark)}
.btn.small{padding:7px 13px;font-size:11.5px}
.btn.ghost{background:none;border:1px solid var(--line);color:var(--mut)}
.btn.ghost:hover{background:var(--card-2);color:#fff;border-color:var(--cyan)}
.btn.danger{background:none;border:1px solid #5c2630;color:var(--bad)}
.btn.danger:hover{background:var(--badbg)}
.btn:disabled{opacity:.4;cursor:default;background:var(--card-2);color:var(--mut)}

input[type=text],input[type=email],input:not([type]),textarea{
  background:var(--black);color:var(--ink);border:1px solid var(--line);
  border-radius:8px;padding:10px 12px;font-size:14px;width:100%}
input:focus,textarea:focus{outline:none;border-color:var(--cyan);
  box-shadow:0 0 0 3px rgba(43,176,232,.18)}
textarea{min-height:70px;resize:vertical}

/* ---- group pills: the tick boxes, made scannable ----
   Twenty-two sections times six groups is a hundred and thirty tick boxes. As
   squares they are a wall; as pills that light up, the answer to "who can see
   this" is readable at a glance. */
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{position:relative;cursor:pointer;user-select:none}
.pill input{position:absolute;opacity:0;width:0;height:0}
.pill span{display:inline-block;border:1px solid var(--line);border-radius:999px;
  padding:5px 12px;font-size:11.5px;font-weight:600;color:var(--dim);
  background:var(--card-2);transition:background .12s,color .12s,border-color .12s}
.pill:hover span{color:var(--ink);border-color:var(--cyan)}
.pill input:checked + span{background:var(--navy);border-color:var(--cyan);
  color:#fff}
.pill input:focus-visible + span{outline:2px solid var(--cyan);outline-offset:2px}

/* ---- state tag ---- */
.state{flex:none;font:700 10px/1.8 var(--font-body);letter-spacing:.08em;
  text-transform:uppercase;border-radius:4px;padding:1px 8px;border:1px solid}
.state.open{color:var(--green);border-color:#1e5c45;background:#0f2a20}
.state.shut{color:var(--amber);border-color:#5c4a20;background:#2b2412}

/* ---- cards ---- */
.card{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--red);
  border-radius:12px;padding:14px 16px 12px;margin:14px 0 0;box-shadow:var(--shadow);
  transition:border-color .16s}
.card:hover{border-top-color:var(--cyan)}
.card.restricted{border-top-color:var(--amber)}
.card.hide{display:none}
.card .top{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.card .label{flex:1;min-width:190px;font-family:var(--font-display);
  font-size:1.08rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
  color:#fff}

.kids{margin-top:12px;border-top:1px solid var(--line);padding-top:10px}
.kids summary{cursor:pointer;color:var(--cyan);font-size:12.5px;font-weight:600;
  padding:3px 0;list-style:none}
.kids summary::-webkit-details-marker{display:none}
/* No backslashes in here. ACCESS_CSS is an ordinary Python string, so a CSS
   escape like the one for a small right arrow is read as an OCTAL escape
   first and the browser is handed the leftovers. The characters themselves
   cannot be misread. */
.kids summary::before{content:"▸ ";display:inline-block;transition:transform .15s}
.kids[open] summary::before{transform:rotate(90deg)}
.kid{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  background:var(--card-2);border-radius:8px;padding:8px 12px;margin-top:6px}
.kid.hide{display:none}
.kid .label{flex:1;min-width:190px;font-size:13px;color:var(--steel);
  font-family:var(--font-body);text-transform:none;letter-spacing:0;font-weight:400}

.save{margin-top:11px;display:flex;align-items:center;gap:12px}
.save .hint{font-size:11.5px;color:var(--dim)}
.card.dirty{border-top-color:var(--cyan)}
.card.dirty .save .hint{color:var(--cyan-light)}

/* ---- people ---- */
.person{display:flex;align-items:center;gap:14px;flex-wrap:wrap;
  background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:9px 13px;margin-top:8px}
.person .who{flex:1;min-width:210px;font-size:13.5px;display:flex;
  align-items:center;gap:9px}
.person .who .av{width:27px;height:27px;border-radius:50%;flex:none;display:grid;
  place-items:center;font:700 10.5px/1 var(--font-body);color:#fff;
  background:linear-gradient(135deg,var(--navy),var(--cyan))}

/* ---- group chips ---- */
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.chip{display:inline-flex;align-items:center;gap:7px;background:var(--card);
  border:1px solid var(--line);border-radius:999px;padding:6px 13px;
  font-size:12.5px;color:var(--steel)}
.chip button{background:none;border:0;color:var(--dim);cursor:pointer;
  font-size:15px;line-height:1;padding:0 0 0 2px}
.chip button:hover{color:var(--red)}
.chip.locked{color:var(--dim);border-style:dashed}

.box{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:16px 18px;margin-top:14px}
.box .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:10px}
.muted{color:var(--mut);font-size:13.5px}
.empty{color:var(--dim);font-size:13.5px;font-style:italic;margin-top:12px}

#filter{max-width:260px}
.count{font-size:12px;color:var(--dim);font-variant-numeric:tabular-nums}

@media (max-width:760px){
  .head .tally{margin-left:0;width:100%}
  .bar{gap:12px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
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
def image(name):
    """The logos, and deliberately NOT behind @protected.

    The sign-in page shows the helmet and the favicon to somebody who has not
    signed in yet - protected, they 302 to the login page and the sign-in
    screen renders with an empty white plate. They are the same logo files the
    public website already serves, so there is nothing here to guard.

    <name> and not <path:name>, so a slash cannot walk out of the folder.
    """
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
#  The filing system plan
# ---------------------------------------------------------------------------
#
# The proposed SharePoint structure, walkable, before any of it is built. It is
# its own page rather than a card on the noticeboard because it is a document
# somebody reads once and argues with, not a link they use every day - and
# because it wants the width.
#
# Gated on the rail link's own key, so hiding "Filing System Plan" on the
# Access screen also shuts the page. One switch, not two: a hidden link over an
# open page is exactly the curtain intranet_access was written to replace.

PLAN_PAGE = "fileplan.html"
PLAN_START = "/* TITAN-PLAN-START */"
PLAN_END = "/* TITAN-PLAN-END */"
PLAN_KEY = "link:homepage::Filing System Plan"

_PLAN = {"json": None}


def _rules():
    """The restriction rules, or none at all if the database cannot be reached.

    all_rules already fails open - a noticeboard that goes blank because
    Postgres hiccupped is worse than one showing a card it should not - but
    conn() raises before all_rules gets the chance to, so the same posture has
    to be taken one step earlier.
    """
    try:
        return intranet_access.all_rules(conn())
    except Exception as e:
        app.logger.warning("no rules available (%s)", e)
        return {}


def _plan_json():
    """The plan, serialised once. It is the same for everybody who may see it."""
    if _PLAN["json"] is None:
        import fileplan
        _PLAN["json"] = fileplan.as_json()
    return _PLAN["json"]


@app.get("/fileplan")
@protected
def fileplan_page():
    email, groups = _who_and_groups()
    if not intranet_access.allows(
            _rules(), PLAN_KEY, groups,
            intranet_access.is_admin(email, groups)):
        app.logger.info("file plan refused for %s", email or "?")
        abort(403)

    path = os.path.join(SITE_DIR, PLAN_PAGE)
    try:
        with open(path, encoding="utf-8") as f:
            page = f.read()
    except OSError:
        app.logger.error("file plan page not found at %s", path)
        abort(404)

    a, b = page.find(PLAN_START), page.find(PLAN_END)
    if a == -1 or b == -1:
        app.logger.error("the file plan page has no markers")
        abort(500)
    page = (page[:a + len(PLAN_START)]
            + "\nvar PLAN = "
            + _plan_json().replace("</", "<\\/")
            + ";\n"
            + page[b:])
    return Response(page, mimetype="text/html",
                    headers={"Cache-Control": "no-store, private",
                             "Vary": "Cookie"})


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


def _pills(key, groups, chosen):
    """One pill per group, for one item.

    A hidden checkbox inside a label: the form posts exactly what it did when
    these were tick boxes, so nothing on the server side changes - but a
    hundred and thirty squares become something you can read.
    """
    return "".join(
        '<label class=pill><input type=checkbox name="rule:%s" value="%s"%s>'
        '<span>%s</span></label>' % (
            html_mod.escape(key), html_mod.escape(g["name"]),
            " checked" if g["name"] in chosen else "",
            html_mod.escape(g["label"]))
        for g in groups)


def _state(shut):
    return ('<span class="state shut">Restricted</span>' if shut
            else '<span class="state open">Everyone</span>')


def _avatar(email):
    return html_mod.escape((email or "?")[:2].upper())


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
            '<form method=post action="/access/person" class=person>'
            '<input type=hidden name=email value="%s">'
            '<span class=who><span class=av>%s</span>%s</span>'
            '<span class=pills>%s</span>'
            '<button class="btn small">Save</button>'
            '<button class="btn small danger" formaction="/access/person/remove"'
            ' name=email value="%s">Remove</button></form>' % (
                html_mod.escape(email), _avatar(email), html_mod.escape(email),
                "".join('<label class=pill><input type=checkbox name=groups '
                        'value="%s"%s><span>%s</span></label>' % (
                            html_mod.escape(g["name"]),
                            " checked" if g["name"] in mine else "",
                            html_mod.escape(g["label"])) for g in groups),
                html_mod.escape(email)))

    # -- what each item shows ---------------------------------------------
    KINDS = {"rail": ("The left rail", "Groups of links down the side of the page."),
             "department": ("Departments", "One card each, and the documents in it."),
             "yard": ("Yard Locations", "Same again, per yard."),
             "tool": ("Tools", "Things that do something rather than open a file."),
             "folder": ("Folders", "SharePoint folders listed at the bottom of the page.")}
    sections, last_kind, restricted = [], None, 0
    for item in intranet_access.inventory(cfg):
        if item["kind"] != last_kind:
            head, blurb = KINDS.get(item["kind"], (item["kind"].title(), ""))
            sections.append(
                '<div class=band><h2>%s</h2><span class=sub>%s</span></div>'
                % (html_mod.escape(head), html_mod.escape(blurb)))
            last_kind = item["kind"]

        keys = [item["key"]] + [ch["key"] for ch in item["children"]]
        shut_here = [k for k in keys if k in rules]
        restricted += len(shut_here)
        card_shut = item["key"] in rules

        kids = ""
        if item["children"]:
            inner = "".join(
                '<div class=kid data-name="%s"><span class=label>%s</span>'
                '<span class=pills>%s</span>%s</div>' % (
                    html_mod.escape(ch["label"].lower()),
                    html_mod.escape(ch["label"]),
                    _pills(ch["key"], groups, rules.get(ch["key"], set())),
                    _state(ch["key"] in rules))
                for ch in item["children"])
            n = len(item["children"])
            shut_kids = sum(1 for ch in item["children"] if ch["key"] in rules)
            kids = ('<details class=kids%s><summary>%d document%s%s</summary>%s'
                    '</details>' % (
                        " open" if shut_kids else "", n, "" if n == 1 else "s",
                        (" \u00b7 %d restricted" % shut_kids) if shut_kids else "",
                        inner))

        sections.append(
            '<form method=post action="/access/rules" class="card%s" '
            'data-name="%s">'
            '<input type=hidden name=keys value="%s">'
            '<div class=top><span class=label>%s</span>'
            '<span class=pills>%s</span>%s</div>%s'
            '<div class=save><button class="btn small">Save</button>'
            '<span class=hint>Tick nobody for everyone.</span></div></form>' % (
                " restricted" if card_shut else "",
                html_mod.escape(item["label"].lower()),
                html_mod.escape("\n".join(keys)),
                html_mod.escape(item["label"]),
                _pills(item["key"], groups, rules.get(item["key"], set())),
                _state(card_shut), kids))

    chips = "".join(
        ('<span class="chip locked">%s<span title="This one cannot be deleted">'
         '\U0001F512</span></span>' % html_mod.escape(g["label"]))
        if g["name"] == intranet_access.ADMIN_GROUP else
        ('<form method=post action="/access/group/remove" class=chip>%s'
         '<input type=hidden name=name value="%s">'
         '<button title="Delete this group">&times;</button></form>' % (
             html_mod.escape(g["label"]), html_mod.escape(g["name"])))
        for g in groups)

    notice = ""
    if request.args.get("ok"):
        notice = '<p class="note ok">%s</p>' % html_mod.escape(request.args["ok"])
    elif request.args.get("err"):
        notice = '<p class="note err">%s</p>' % html_mod.escape(request.args["err"])

    return _html(ACCESS_HTML % {
        "css": ACCESS_CSS,
        "icon": _brand_bit("icon"),
        "who": html_mod.escape(session.get("email") or ""),
        "av": _avatar(session.get("email")),
        "people": "".join(people) or
                  '<p class=empty>Nobody has been given a group yet &mdash; so '
                  'everybody signing in sees whatever has not been restricted.</p>',
        "groups": chips,
        "sections": "".join(sections),
        "notice": notice,
        "n_groups": len(groups),
        "n_people": len(members),
        "n_rules": restricted,
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
<title>Access &mdash; Titan Enterprises Intranet</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=icon href="%(icon)s">
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Inter:wght@400;600;700&display=swap" rel=stylesheet>
<style>
%(css)s
</style>

<div class=bar>
  <img class=logo src="/images/titan-enterprises-logo.png" alt="Titan Enterprises">
  <span class=divider></span>
  <span>
    <span class=kicker>Intranet</span>
    <span class=name>Access</span>
  </span>
  <span class=sp></span>
  <span class=who><span class=av>%(av)s</span>%(who)s</span>
  <a class=back href="/">&larr; Back to the intranet</a>
</div>

<div class=wrap>
  <div class=head>
    <div>
      <h1>Who sees what</h1>
      <div class=rule></div>
      <p>Everyone with a Titan account gets the intranet. Groups decide how much
      of it. Anything you have not restricted is visible to everybody &mdash;
      that is the default, and it is why a new starter is useful on day one.</p>
    </div>
    <div class=tally>
      <div><b>%(n_groups)s</b><span>Groups</span></div>
      <div><b>%(n_people)s</b><span>People</span></div>
      <div><b>%(n_rules)s</b><span>Restrictions</span></div>
    </div>
  </div>

  %(notice)s

  <div class=band>
    <h2>Groups</h2>
    <span class=sub>People go in groups; groups are what sections are opened to.</span>
  </div>
  <div class=chips>%(groups)s</div>
  <form method=post action="/access/group" class=box>
    <div class=row>
      <input name=label placeholder="Yard Managers" style="max-width:250px">
      <input name=name placeholder="yard-managers (optional)" style="max-width:250px">
      <button class="btn small">Add group</button>
    </div>
    <p class=muted style="margin-top:10px">The second box is the short name used
    in the database. Leave it blank and it is made from the first.</p>
  </form>

  <div class=band>
    <h2>People</h2>
    <span class=sub>Somebody in no group still sees everything unrestricted.</span>
  </div>
  %(people)s
  <form method=post action="/access/people/add" class=box>
    <textarea name=emails placeholder="paste addresses &mdash; one per line, or comma separated"></textarea>
    <div class=row>
      <span class=muted>Put them all in:</span>
      <span class="pills" id=addgroups></span>
      <button class="btn small">Add people</button>
    </div>
  </form>

  <div class=band>
    <h2>What each section shows</h2>
    <span class=sub>Tick nobody and it is open to everyone. Tick a group and only
    that group sees it. Shutting a card hides its documents too &mdash; so to give
    everybody a few rows out of a restricted area, leave the card open and
    restrict the rows.</span>
    <span class=tools>
      <input id=filter placeholder="Filter&hellip;" autocomplete=off>
      <button class="btn small ghost" type=button id=expand>Expand all</button>
    </span>
  </div>
  %(sections)s
</div>

<script>
(function(){
  /* -- the add-people form needs the same pills as the rows above it, and
        building them here keeps one copy of the group list. -- */
  var first = document.querySelector('form.person .pills');
  var into  = document.getElementById('addgroups');
  if (into){
    if (first){
      into.innerHTML = first.innerHTML.replace(/ checked/g, '');
    } else {
      var out = '';
      document.querySelectorAll('.chip').forEach(function(ch){
        var hidden = ch.querySelector('input[name=name]');
        var label = ch.childNodes[0].nodeValue.trim();
        var name = hidden ? hidden.value
                          : label.toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
        out += '<label class=pill><input type=checkbox name=groups value="' +
               name + '"><span>' + label + '</span></label>';
      });
      into.innerHTML = out;
    }
  }

  /* -- Save only matters once something has changed. Saying so stops the
        other twenty-one Save buttons looking like work you still owe. -- */
  document.querySelectorAll('form.card').forEach(function(card){
    var hint = card.querySelector('.save .hint');
    var was  = hint ? hint.textContent : '';
    card.addEventListener('change', function(){
      card.classList.add('dirty');
      if (hint) hint.textContent = 'Not saved yet.';
    });
  });

  /* -- filter: twenty-two sections and a hundred and forty-nine documents is
        more than anybody wants to scroll. Matching a document opens the card
        it lives in. -- */
  var box = document.getElementById('filter');
  if (box){
    box.addEventListener('input', function(){
      var q = box.value.trim().toLowerCase();
      document.querySelectorAll('form.card').forEach(function(card){
        var hitCard = !q || (card.dataset.name || '').indexOf(q) !== -1;
        var kidHit = false;
        card.querySelectorAll('.kid').forEach(function(kid){
          var hit = !q || hitCard || (kid.dataset.name || '').indexOf(q) !== -1;
          kid.classList.toggle('hide', !hit);
          if (hit && q && !hitCard) kidHit = true;
        });
        card.classList.toggle('hide', !(hitCard || kidHit));
        var det = card.querySelector('details');
        if (det && q && kidHit) det.open = true;
      });
    });
    document.addEventListener('keydown', function(e){
      if (e.key === '/' && document.activeElement !== box &&
          document.activeElement.tagName !== 'INPUT' &&
          document.activeElement.tagName !== 'TEXTAREA'){
        e.preventDefault(); box.focus();
      }
    });
  }

  var expand = document.getElementById('expand');
  if (expand){
    expand.addEventListener('click', function(){
      var any = document.querySelector('details.kids:not([open])');
      document.querySelectorAll('details.kids').forEach(function(d){ d.open = !!any; });
      expand.textContent = any ? 'Collapse all' : 'Expand all';
    });
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


def _packet_order(folder):
    """The print order for one company's packets, out of config.json.

    In the config rather than in this file, because the order is HR's to
    change: they are the ones who know that Contacts and ADP come first and the
    Safe Driving packet comes last. Editing a list and pushing is a smaller ask
    than editing Python, and no folder without an entry is affected.
    """
    cfg = site_config() or {}
    orders = (cfg.get("orientation") or {}).get("order") or {}
    return orders.get(folder) or orders.get("*") or []


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
    folder = request.args.get("folder") or ""
    try:
        lib = _orientation_lib()
        return jsonify(orientation.listing(lib, folder, _packet_order(folder)))
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
                                info=info,
                                order=_packet_order(body.get("folder") or ""))
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
    # The same shape the other Titan sites report, so the two can be compared
    # side by side: it says whether sign-in is switched on and which settings
    # it thinks are absent, rather than only which version is deployed.
    try:
        detail["auth"] = auth.health()
    except Exception:
        detail["auth"] = {"version": getattr(auth, "VERSION", "unknown")}
    detail["site"] = "intranet"
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
