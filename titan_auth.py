"""titan-sso-v1: one sign-in for every Titan site.

This is a drop-in module. The same file is copied into each app - the portal,
the tickets site, the driver form, the dispatch board - and every one of them
signs people in the same way against the same Entra app registration. Copied
rather than packaged because these are separate repositories that deploy on
their own schedules, and a shared package would mean a version of this file can
be live on one site and not another with nothing saying so. `VERSION` below is
printed on each site's /healthz so you can see at a glance which sites are
behind.

Grew out of the tickets site's auth.py, which is the code that has actually
been through a production sign-in. The OAuth flow here is that code, unchanged
in its essentials. What is new is the answer to "they signed in at the portal,
why are they being asked again":


How being signed in everywhere actually works
---------------------------------------------
A cookie belongs to one hostname. tickets.tetransports.com cannot read the
portal's cookie and never will, so there is no version of this where one login
cookie covers every site. Something outside all of them has to hold the fact
that this person signed in. Two things can, and this module uses both:

**Microsoft's own session (the mechanism).** Signing in at the portal leaves a
session at login.microsoftonline.com. When the tickets site then redirects
there with `prompt=none`, Microsoft sees that session, asks nothing, and
bounces straight back with a code. The person sees a flicker. If there is no
session, Microsoft returns `login_required` instead of showing a login box, and
the site falls back to a normal sign-in. This is the real mechanism: it works
across any hostname, survives the browser being closed, and is the same thing
that makes Outlook and Teams not ask twice.

**A signed ticket on .tetransports.com (the shortcut).** Every site is a
subdomain of one parent domain, so a cookie set on `.tetransports.com` is
readable by all of them. On sign-in the portal writes one holding only an email
address, a display name and a timestamp, signed with a key the sites share. A
site that finds a valid one adopts it and skips the round trip to Microsoft
entirely. It saves about a second and, more usefully, it works on a request
that cannot be redirected.

The shortcut is off unless SSO_SECRET and SSO_COOKIE_DOMAIN are both set, and
the mechanism above is correct without it. If the shared key ever worries you,
delete the two settings and everything still works, a little slower.

The ticket is deliberately thin: identity and nothing else, no roles, no
permissions, twelve hours by default. Each site still decides for itself what
that person may do - see `may_use()`. A cookie that granted access rather than
merely asserting a name would mean one compromised site could mint access to
all of them, and short of that, that revoking someone would not take effect
until their cookie expired.


On not verifying the id_token signature
---------------------------------------
Inherited from the tickets site, and still true here. The token is not accepted
from the browser; it is fetched by this server from Microsoft's token endpoint
over TLS, in a request authenticated with our client secret. The channel
already establishes who sent it and that it was not altered. What the channel
does not establish is that the token is meant for us and is current, so
audience, issuer, tenant, expiry and nonce are all checked by hand below on
every sign-in.

The SSO ticket is a different matter - that one *does* arrive from the browser,
so it is signed with HMAC and the signature is checked in constant time before
a single field in it is believed.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "titan-sso-v1"

TENANT = (os.environ.get("TENANT_ID") or "").strip()

# AUTH_CLIENT_ID is the switch, and it has no fallback. That is deliberate and
# it is a correction carried over from the tickets site: it used to fall back to
# GRAPH_CLIENT_ID, which meant deploying this code would switch sign-in on by
# itself, in the same minute, with no redirect URI registered yet - the passcode
# form gone and nobody able to get in. A deploy that locks the office out is not
# a rollout, whatever the release notes said.
#
# So turning this on is one setting somebody types on purpose. The secret may
# still be borrowed, because borrowing a secret cannot start anything.
CLIENT_ID = (os.environ.get("AUTH_CLIENT_ID") or "").strip()
CLIENT_SECRET = (os.environ.get("AUTH_CLIENT_SECRET")
                 or os.environ.get("GRAPH_CLIENT_SECRET") or "").strip()

# Where Microsoft sends people back to. Must match a redirect URI on the app
# registration exactly, character for character. Left empty it is worked out
# from the request, which is right once a site is on its final hostname and
# wrong the moment it is reachable at two.
REDIRECT = (os.environ.get("AUTH_REDIRECT") or "").strip()

# Which site this is, in the access tables. Every app sets its own.
SITE = (os.environ.get("SITE_SLUG") or "").strip().lower()

# The access tables live in their own Postgres schema, shared by every site.
# Named explicitly in every query here rather than left to the search path,
# because each app points its search path at its own schema - the tickets app at
# `ocr` - and an unqualified `portal_sites` would resolve to nothing there. That
# failure would be caught by may_use()'s except and read as "denied", which is
# safe but would have somebody debugging permissions rather than a search path.
PORTAL_SCHEMA = (os.environ.get("PORTAL_SCHEMA") or "portal").strip()
if not PORTAL_SCHEMA.replace("_", "").isalnum():
    raise SystemExit("PORTAL_SCHEMA must be letters, digits and underscores; "
                     "got %r" % PORTAL_SCHEMA)
_P = '"%s".' % PORTAL_SCHEMA

# The shortcut. Both must be set or it stays off.
SSO_SECRET = (os.environ.get("SSO_SECRET") or "").strip()
SSO_DOMAIN = (os.environ.get("SSO_COOKIE_DOMAIN") or "").strip()
SSO_COOKIE = "titan_sso"
SSO_TTL = int(os.environ.get("SSO_TTL_HOURS") or 12) * 3600

# A last-resort override, and the only thing that ignores the access tables.
# Written for the morning the database is unreachable and somebody still has to
# get into the portal to find out why.
BREAKGLASS = [e.strip().lower()
              for e in (os.environ.get("PORTAL_ADMINS") or "").split(",")
              if e.strip()]

SCOPES = "openid profile email"
CLOCK_SKEW = 120          # seconds of tolerance on expiry
SILENT_COOLDOWN = 300     # don't re-attempt a failed silent sign-in for this long

# ---------------------------------------------------------------------------
#  Working on this without Entra
# ---------------------------------------------------------------------------
# A sign-in that only works against a real Entra registration cannot be looked
# at on a laptop, and "deploy it to see whether the page is right" is a bad way
# to build a page. So there is a local mode that skips Microsoft and lets you
# say who you are.
#
# That is a backdoor, and the only version of it worth having is one that cannot
# possibly be open in production. Two independent locks, either of which is
# enough on its own:
#
#   1. PORTAL_LOCAL_SIGNIN must be set. Nobody sets that on Azure by accident.
#   2. The request must have arrived at localhost, with no proxy in front.
#
# The second is the one that actually protects you, because it does not depend
# on anybody remembering anything. Azure App Service always terminates at a
# front door and forwards, so a request there always carries X-Forwarded-* and
# a real hostname. Even if this setting were copied into the live app settings
# by mistake - the obvious way this kind of thing goes wrong - every request in
# Azure fails lock 2 and the backdoor stays shut.
#
# It is also loud: the sign-in page says so, every page carries a banner, and
# /healthz reports it. A quiet backdoor is the dangerous kind.
LOCAL_SIGNIN = (os.environ.get("PORTAL_LOCAL_SIGNIN") or "").strip().lower() \
    in ("1", "true", "yes", "on")

# Headers that mean something is in front of this app. Azure sets these; a
# Flask dev server on a laptop does not.
_PROXY_HEADERS = ("X-Forwarded-Host", "X-Forwarded-For", "X-Forwarded-Proto",
                  "X-Arr-Ssl", "X-Client-Ip", "Forwarded")

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "[::1]")


def local_signin_ok(request):
    """Whether the no-Entra sign-in may be used for this request.

    Both locks, checked every time rather than worked out once at import,
    because the host is a property of the request and not of the process.
    """
    if not LOCAL_SIGNIN:
        return False
    if any(request.headers.get(h) for h in _PROXY_HEADERS):
        return False
    host = (urllib.parse.urlsplit(request.url_root).hostname or "").lower()
    return host in _LOCAL_HOSTS


class AuthError(Exception):
    """Something about the sign-in did not add up. The message is shown to the
    person, so it says what to do rather than what went wrong internally."""


class NeedsInteraction(AuthError):
    """Microsoft has no session for this browser, so a silent attempt cannot
    succeed and the person has to actually sign in.

    Its own class because it is not a failure - it is the expected answer for
    somebody arriving in the morning, and the caller must tell it apart from a
    real error. Treating it as an error is how you get a site that shows
    "sign-in failed" to everyone who opens it first thing.
    """


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

def enabled():
    """Whether Microsoft sign-in is configured.

    Deliberately not all-or-nothing at deploy time: the code can ship before the
    app registration is ready, and a site carries on however it did until the
    three settings are filled in. That keeps the switch a settings change rather
    than a release.
    """
    return bool(TENANT and CLIENT_ID and CLIENT_SECRET)


def shortcut_enabled():
    return bool(SSO_SECRET and SSO_DOMAIN)


def missing():
    """Which settings are absent, for the status page."""
    return [n for n, v in (("TENANT_ID", TENANT),
                           ("AUTH_CLIENT_ID", CLIENT_ID),
                           ("AUTH_CLIENT_SECRET (or GRAPH_CLIENT_SECRET)",
                            CLIENT_SECRET)) if not v]


def health():
    """One dict for /healthz, so you can see what a site thinks it is set up to
    do without signing in to it."""
    out = {
        "version": VERSION,
        "site": SITE or None,
        "sign_in": "on" if enabled() else "off",
        "missing": missing(),
        "shortcut": "on" if shortcut_enabled() else "off",
    }
    if LOCAL_SIGNIN:
        # Reported even though it cannot work in Azure, because the useful thing
        # to know from a health check is that somebody left the setting on -
        # ideally before they wonder why. Never silent.
        out["local_signin_setting"] = "SET - only usable from localhost"
    return out


def _authorize_url():
    return "https://login.microsoftonline.com/%s/oauth2/v2.0/authorize" % TENANT


def _token_url():
    return "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % TENANT


def _logout_url(back_to):
    return ("https://login.microsoftonline.com/%s/oauth2/v2.0/logout"
            "?post_logout_redirect_uri=%s"
            % (TENANT, urllib.parse.quote(back_to, safe="")))


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64url(txt):
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def redirect_uri(request):
    """The callback address, as Microsoft must have it registered.

    Azure App Service terminates TLS at the front door and talks to the
    container over plain HTTP, so Flask sees a http:// URL and builds a redirect
    URI that does not match the registration - which fails at sign-in with a
    message about the reply URL, and sends people looking at Entra when the app
    is what is wrong. Forced to https unless it is genuinely local.
    """
    if REDIRECT:
        return REDIRECT
    url = request.url_root.rstrip("/") + "/auth/callback"
    host = urllib.parse.urlsplit(url).hostname or ""
    if url.startswith("http://") and host not in ("localhost", "127.0.0.1"):
        url = "https://" + url[len("http://"):]
    return url


def safe_next(value, default="/"):
    """A path on this site, or the default.

    Everything that carries "where were you heading" through a redirect goes
    through here. "Come back to whatever this says" is how an open redirect gets
    built by accident, and the accident looks exactly like working code.
    """
    v = (value or "").strip()
    if not v.startswith("/") or v.startswith("//") or v.startswith("/\\"):
        return default
    return v


# ---------------------------------------------------------------------------
#  The OAuth round trip
# ---------------------------------------------------------------------------

def begin(session, request, next_url=None, silent=False):
    """Start a sign-in. Returns the URL to send the browser to.

    `silent=True` adds prompt=none: Microsoft either completes it without
    showing anything, or refuses with login_required, which surfaces at the
    callback as NeedsInteraction. It never shows a login box in this mode, so it
    is safe to do on a page load.

    state, nonce and the PKCE verifier are kept in the session cookie, which is
    signed, so a reply that did not come from a sign-in this browser started is
    rejected at the callback.
    """
    if not enabled():
        raise AuthError("Microsoft sign-in is not configured on this site.")
    st = {
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "verifier": secrets.token_urlsafe(64),
        "next": safe_next(next_url),
        "silent": bool(silent),
        "started": int(time.time()),
    }
    session["oidc"] = st
    challenge = _b64url(hashlib.sha256(st["verifier"].encode("ascii")).digest())
    q = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri(request),
        "response_mode": "query",
        "scope": SCOPES,
        "state": st["state"],
        "nonce": st["nonce"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if silent:
        q["prompt"] = "none"
    return _authorize_url() + "?" + urllib.parse.urlencode(q)


def _post_token(data):
    body = urllib.parse.urlencode(data).encode("ascii")
    req = urllib.request.Request(_token_url(), data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        try:
            j = json.loads(detail)
            detail = j.get("error_description") or j.get("error") or detail
        except Exception:
            pass
        # The ones that actually happen, named so nobody goes hunting.
        if "AADSTS50011" in detail:
            raise AuthError(
                "This site's address is not on the app registration's list of "
                "redirect URIs. Add %s under Authentication -> Web."
                % data.get("redirect_uri"))
        if "AADSTS7000215" in detail or "invalid_client" in detail:
            raise AuthError("The client secret is wrong or has expired. Make a "
                            "new one in Entra and update the app setting. Note "
                            "that every Titan site shares this secret, so all "
                            "of them are affected.")
        raise AuthError("Microsoft would not complete the sign-in: " +
                        detail.split(" Trace ID")[0][:300])
    except Exception as e:
        raise AuthError("Could not reach Microsoft to complete the sign-in: %s"
                        % e)


def _claims(id_token):
    parts = id_token.split(".")
    if len(parts) != 3:
        raise AuthError("Microsoft returned a token this site could not read.")
    try:
        return json.loads(_unb64url(parts[1]).decode("utf-8"))
    except Exception:
        raise AuthError("Microsoft returned a token this site could not read.")


# The errors that mean "nobody is signed in with Microsoft right now", as
# opposed to "the sign-in is broken". consent_required is in the list because a
# silent attempt cannot show a consent screen either; it needs a person.
_QUIET = ("login_required", "interaction_required", "consent_required",
          "account_selection_required")


def complete(session, request, args):
    """Finish a sign-in. Returns {"email", "name", "silent"}.

    Raises NeedsInteraction if a silent attempt found no Microsoft session, and
    AuthError for everything else.
    """
    st = session.get("oidc")
    if not st:
        raise AuthError("That sign-in took too long, or was started in another "
                        "window. Try again.")

    if args.get("error"):
        session.pop("oidc", None)
        err = str(args.get("error") or "")
        if err in _QUIET:
            raise NeedsInteraction("Not signed in with Microsoft yet.")
        raise AuthError(args.get("error_description") or err)

    # Constant-time, because state is the thing standing between this callback
    # and one somebody else arranged for you to visit.
    if not hmac.compare_digest(str(args.get("state") or ""), st["state"]):
        session.pop("oidc", None)
        raise AuthError("That sign-in did not start here. Try again from the "
                        "sign-in page.")

    code = args.get("code")
    if not code:
        session.pop("oidc", None)
        raise AuthError("Microsoft did not return a sign-in code.")

    tok = _post_token({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(request),
        "code_verifier": st["verifier"],
        "scope": SCOPES,
    })
    session.pop("oidc", None)

    id_token = tok.get("id_token")
    if not id_token:
        raise AuthError("Microsoft did not return an identity token.")
    c = _claims(id_token)

    # See the note at the top of this file for why these are checked by hand and
    # the signature is not.
    if c.get("aud") != CLIENT_ID:
        raise AuthError("That sign-in was issued for a different application.")
    if c.get("tid") and c["tid"] != TENANT:
        raise AuthError("That account is not in this company's directory.")
    iss = str(c.get("iss") or "")
    if TENANT not in iss or not iss.startswith("https://login.microsoftonline.com/"):
        raise AuthError("That sign-in did not come from this company's directory.")
    if not hmac.compare_digest(str(c.get("nonce") or ""), st["nonce"]):
        raise AuthError("That sign-in could not be matched to this browser. "
                        "Try again.")
    exp = c.get("exp")
    if not exp or int(exp) + CLOCK_SKEW < time.time():
        raise AuthError("That sign-in has expired. Try again.")

    email = (c.get("preferred_username") or c.get("email") or c.get("upn") or "")
    email = email.strip().lower()
    if not email or "@" not in email:
        raise AuthError("That account has no email address on it, so there "
                        "would be no way to record who did what.")

    return {"email": email,
            "name": (c.get("name") or "").strip() or email,
            "silent": bool(st.get("silent")),
            "next": safe_next(st.get("next"))}


def logout_url(back_to):
    """Sign out of Microsoft as well, for the portal's "sign out everywhere".

    Worth knowing what this actually does: it ends the Microsoft session, which
    takes Outlook and Teams in that browser with it. That is right for "sign out
    of everything on this machine" and wrong for an ordinary sign-out, so the
    portal offers both and the individual sites only ever do the local one.
    """
    return _logout_url(back_to)


# ---------------------------------------------------------------------------
#  The shared ticket on .tetransports.com
# ---------------------------------------------------------------------------
#  Format: base64url(json payload) + "." + base64url(hmac-sha256 of that)
#
#  Its own signing rather than Flask's itsdangerous because every site has to
#  read it and they do not share a SECRET_KEY - each site's own session cookie
#  stays signed with its own key, so a site being compromised does not hand over
#  the others' sessions. Only this one narrow, identity-only value crosses.

def mint_ticket(email, name):
    """A ticket asserting who this is. None when the shortcut is off."""
    if not shortcut_enabled():
        return None
    payload = json.dumps({"e": email, "n": name, "t": int(time.time())},
                         separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = _b64url(payload)
    sig = hmac.new(SSO_SECRET.encode("utf-8"), body.encode("ascii"),
                   hashlib.sha256).digest()
    return body + "." + _b64url(sig)


def read_ticket(raw):
    """{"email", "name"} from a ticket, or None.

    Returns None for anything at all doubtful - bad signature, wrong shape,
    expired, no email. Never raises: this runs on every request on every site
    and a malformed cookie must mean "not signed in", not a 500.
    """
    if not shortcut_enabled() or not raw or "." not in raw:
        return None
    body, _, sig = raw.partition(".")
    try:
        want = hmac.new(SSO_SECRET.encode("utf-8"), body.encode("ascii"),
                        hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64url(sig), want):
            return None
        d = json.loads(_unb64url(body).decode("utf-8"))
        issued = int(d.get("t") or 0)
        # Both directions. A ticket from the future is either a clock that
        # disagrees or one somebody made up, and neither is worth honouring.
        if issued <= 0 or issued > time.time() + CLOCK_SKEW:
            return None
        if issued + SSO_TTL < time.time():
            return None
        email = str(d.get("e") or "").strip().lower()
        if not email or "@" not in email:
            return None
        return {"email": email, "name": str(d.get("n") or "").strip() or email}
    except Exception:
        return None


def set_ticket(response, email, name):
    """Write the ticket onto a response. No-op when the shortcut is off."""
    tk = mint_ticket(email, name)
    if tk:
        response.set_cookie(SSO_COOKIE, tk, domain=SSO_DOMAIN, max_age=SSO_TTL,
                            secure=True, httponly=True, samesite="Lax", path="/")
    return response


def clear_ticket(response):
    if SSO_DOMAIN:
        response.set_cookie(SSO_COOKIE, "", domain=SSO_DOMAIN, max_age=0,
                            secure=True, httponly=True, samesite="Lax", path="/")
    return response


# ---------------------------------------------------------------------------
#  What a site asks on an unauthenticated request
# ---------------------------------------------------------------------------

def ticket_for(request):
    """The identity asserted by the shared cookie on this request, or None."""
    return read_ticket(request.cookies.get(SSO_COOKIE))


def should_try_silent(session, request):
    """Whether to bounce this request through Microsoft to see if they are
    already signed in.

    The three noes matter more than the yes:

    - Not if we tried recently and it failed. Without this the site is a
      redirect loop for anybody genuinely signed out: no session, silent
      attempt, login_required, render the sign-in page, and if anything on that
      page triggers the check again round it goes. The cooldown makes a failed
      attempt cost one round trip every five minutes rather than every request.

    - Not for fetch() and not for POST. A redirect to Microsoft answered to
      fetch() is followed silently and the caller gets Microsoft's HTML where it
      expected JSON; a POST loses its body on the way. Those get a 401 and let
      the page say the session ran out.

    - Not while a sign-in is already in flight, which is what a request arriving
      with `oidc` set means.
    """
    if not enabled():
        return False
    if request.method != "GET":
        return False
    if session.get("oidc"):
        return False
    last = session.get("sso_tried") or 0
    try:
        last = int(last)
    except (TypeError, ValueError):
        last = 0
    if last and last + SILENT_COOLDOWN > time.time():
        return False
    return True


def note_silent_attempt(session):
    session["sso_tried"] = int(time.time())


def clear_silent_attempt(session):
    session.pop("sso_tried", None)


def is_fetch(request):
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


# ---------------------------------------------------------------------------
#  Whether this person may use this site
# ---------------------------------------------------------------------------

def may_use(conn, email, slug=None):
    """The access decision, asked by every site about itself.

    Signing in and being allowed in are two questions, and this module answers
    only the second by asking the portal's tables. Every site asks for itself:
    the portal hiding a tile is a courtesy, not a control, and a site that
    trusted the portal to have done the checking would be open to anyone in the
    tenant who typed its address.

    Fails closed on a database error, except for the break-glass list. An
    unreachable database must not become "everybody is an admin", and must also
    not lock out the person who has to go and fix it.
    """
    email = (email or "").strip().lower()
    if not email:
        return False
    if email in BREAKGLASS:
        return True
    slug = (slug or SITE or "").strip().lower()
    if not slug:
        # No site configured means nothing to check against. Signed in is the
        # most this module can honestly say.
        return True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT open_to_all FROM %sportal_sites WHERE slug=%%s"
                        % _P, (slug,))
            row = cur.fetchone()
            if row is None:
                # A site not in the table is not a site anybody has been given
                # access to. Fails closed, and the portal's own page will show
                # it as unregistered so the cause is visible.
                return False
            # Works whether the caller's connection hands back dicts or tuples;
            # the apps differ and this module is copied into all of them.
            if (row["open_to_all"] if isinstance(row, dict) else row[0]):
                return True
            cur.execute("SELECT 1 FROM %sportal_access "
                        "WHERE slug=%%s AND email=%%s" % _P, (slug, email))
            return cur.fetchone() is not None
    except Exception:
        return False
