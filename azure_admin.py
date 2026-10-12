"""admin-site-v1: the Azure side of /admin - each Titan web app's settings, and
a restart button.

Every switch the sites run on (which mailboxes are read, whether the dispatch
board is written to, the AI reader, the skip list) is an App Service setting,
and until now changing one meant the Azure portal on a computer. This talks to
Azure's management API with one service login (an app registration given the
Website Contributor role on the Titan web apps), so the admin page can show and
change them from a phone.

What it will not do:

  * hand a secret to the browser. A setting whose name says it is a key,
    secret, password, token or connection string - or whose value carries a
    password in a URL - leaves here as "set, 64 characters" and nothing else.
    It can be replaced with a new value; it cannot be read back.
  * change a guarded setting (the database, sign-in, the session key, the
    site's short name) without the app's name typed out to confirm.
  * point a test app or a staging slot at the database the production apps use.
    That rule is older than this file (the test app must never touch the
    production database); here it is enforced, not remembered.

Settings are written read-modify-write: Azure's PUT replaces the whole list, so
every change reads the current list first and sends it back with the one
change. A change restarts the app (Azure does that itself) - the page says so.

Settings it needs, on the intranet app only:

    ADMIN_AZ_CLIENT_ID       the service login's application (client) id
    ADMIN_AZ_CLIENT_SECRET   its secret
    ADMIN_AZ_SUBSCRIPTION    the subscription the web apps are in
    TENANT_ID                already set for sign-in (or ADMIN_AZ_TENANT)
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://management.azure.com"
VER = "2023-12-01"

SECRET_NAME = re.compile(r"(KEY|SECRET|PASS|PWD|TOKEN|CREDENTIAL|PRIVATE|CONNECTION|DATABASE_URL|DSN|CERT)",
                         re.I)
URL_WITH_PASSWORD = re.compile(r"://[^/\s:@]+:[^/\s@]+@")

# Changing one of these can lock everybody out of a site or point it at the
# wrong data. Allowed, but only with the app's name typed to confirm.
GUARDED = {"DATABASE_URL", "SECRET_KEY", "TENANT_ID", "AUTH_CLIENT_ID", "AUTH_CLIENT_SECRET", "AUTH_REDIRECT",
           "SSO_SECRET", "SSO_COOKIE_DOMAIN", "SITE_SLUG", "AP_SITE_SLUG", "HR_SITE_SLUG", "PORTAL_ADMINS",
           "PORTAL_SCHEMA", "SITE_ROLE", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET", "SUPABASE_SERVICE_KEY",
           "SUPABASE_URL", "ANTHROPIC_API_KEY", "ADMIN_AZ_CLIENT_ID", "ADMIN_AZ_CLIENT_SECRET",
           "ADMIN_AZ_SUBSCRIPTION", "ADMIN_SITE_USERS"}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class AzureError(Exception):
    pass


def missing():
    """The settings this needs and does not have - the page shows the setup steps."""
    out = [n for n in ("ADMIN_AZ_CLIENT_ID", "ADMIN_AZ_CLIENT_SECRET", "ADMIN_AZ_SUBSCRIPTION")
           if not (os.environ.get(n) or "").strip()]
    if not (os.environ.get("ADMIN_AZ_TENANT") or os.environ.get("TENANT_ID") or "").strip():
        out.append("TENANT_ID")
    return out


def is_secret(name, value=""):
    return bool(SECRET_NAME.search(name or "") or URL_WITH_PASSWORD.search(str(value or "")))


def is_guarded(name):
    n = (name or "").upper()
    return n in GUARDED or n.startswith("WEBSITE_") or n.startswith("SCM_") or n.startswith("APPSETTING_")


def shown(name, value):
    """What the browser may see of one setting."""
    v = "" if value is None else str(value)
    if is_secret(name, v):
        return {"name": name, "secret": True, "value": None,
                "hint": "set, %d characters" % len(v) if v else "set, empty", "guarded": is_guarded(name)}
    return {"name": name, "secret": False, "value": v, "guarded": is_guarded(name)}


def is_test_target(app):
    """A test app or a staging slot - never to share production's database."""
    a = (app or "").lower()
    return "/" in a or a.endswith("-test") or "-test-" in a or "staging" in a


def _urlopen(method, url, headers, body):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": {"message": raw.decode("utf-8", "replace")[:300]}}


class Azure:
    """One service login. `http(method, url, headers, body) -> (status, json)` is
    swapped out in the tests; nothing here talks to Azure in them."""

    def __init__(self, http=None):
        self.http = http or _urlopen
        self.tenant = (os.environ.get("ADMIN_AZ_TENANT") or os.environ.get("TENANT_ID") or "").strip()
        self.client = (os.environ.get("ADMIN_AZ_CLIENT_ID") or "").strip()
        self.secret = (os.environ.get("ADMIN_AZ_CLIENT_SECRET") or "").strip()
        self.sub = (os.environ.get("ADMIN_AZ_SUBSCRIPTION") or "").strip()
        self._tok, self._tok_until = None, 0
        self._ids = {}

    # -- plumbing ----------------------------------------------------------
    def _token(self):
        if self._tok and time.time() < self._tok_until - 60:
            return self._tok
        if missing():
            raise AzureError("the admin site's Azure login is not set up yet (%s)" % ", ".join(missing()))
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": self.client,
                                       "client_secret": self.secret,
                                       "scope": API + "/.default"}).encode()
        url = "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % urllib.parse.quote(self.tenant)
        if self.http is _urlopen:
            req = urllib.request.Request(url, data=body, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    j = json.loads(r.read())
            except urllib.error.HTTPError as e:
                raise AzureError("Azure refused the admin site's login (HTTP %d) - check ADMIN_AZ_CLIENT_ID "
                                 "and its secret" % e.code)
        else:
            st, j = self.http("TOKEN", url, {}, None)
            if st != 200:
                raise AzureError("Azure refused the admin site's login (HTTP %d)" % st)
        self._tok = j.get("access_token")
        self._tok_until = time.time() + int(j.get("expires_in") or 3000)
        if not self._tok:
            raise AzureError("Azure gave no token")
        return self._tok

    def _call(self, method, path, body=None):
        url = path if path.startswith("http") else API + path
        url += ("&" if "?" in url else "?") + "api-version=" + VER
        st, j = self.http(method, url, {"Authorization": "Bearer " + self._token(),
                                        "Content-Type": "application/json"}, body)
        if st >= 400:
            msg = ((j or {}).get("error") or {}).get("message") or ("HTTP %d" % st)
            if st == 403:
                msg = ("the admin site's Azure login is not allowed to do that - give it the Website "
                       "Contributor role on this app (%s)" % msg[:160])
            raise AzureError(msg[:300])
        return j or {}

    # -- the apps ----------------------------------------------------------
    def apps(self):
        """Every web app in the subscription, and each one's slots, as names
        like 'titantickets' and 'titantickets/staging'."""
        j = self._call("GET", "/subscriptions/%s/providers/Microsoft.Web/sites" % self.sub)
        out = []
        for s in j.get("value") or []:
            if "app" not in (s.get("kind") or "app"):
                continue
            name, sid = s.get("name"), s.get("id")
            p = s.get("properties") or {}
            self._ids[name] = sid
            out.append({"name": name, "state": p.get("state"), "host": (p.get("defaultHostName") or ""),
                        "hosts": [h for h in (p.get("hostNames") or []) if h],
                        "group": (sid or "").split("/resourceGroups/")[-1].split("/")[0]})
            try:
                slots = self._call("GET", sid + "/slots").get("value") or []
            except AzureError:
                slots = []
            for sl in slots:
                sn = (sl.get("name") or "").split("/")[-1]
                full = "%s/%s" % (name, sn)
                self._ids[full] = sl.get("id")
                sp = sl.get("properties") or {}
                out.append({"name": full, "state": sp.get("state"), "host": sp.get("defaultHostName") or "",
                            "hosts": [h for h in (sp.get("hostNames") or []) if h], "slot": True,
                            "group": out[-1]["group"] if out else ""})
        return sorted(out, key=lambda a: a["name"])

    def _id(self, app):
        if app not in self._ids:
            self.apps()
        if app not in self._ids:
            raise AzureError("there is no web app called %s" % app)
        return self._ids[app]

    def settings(self, app):
        """{name: value} - the real values. Never sent to the browser as they are."""
        return dict((self._call("POST", self._id(app) + "/config/appsettings/list").get("properties") or {}))

    def shown_settings(self, app):
        return [shown(k, v) for k, v in sorted(self.settings(app).items(), key=lambda kv: kv[0].lower())]

    def change(self, app, name, value=None, delete=False, confirm=""):
        """Set (or delete) one setting. Returns what it was, as shown()."""
        name = (name or "").strip()
        if not NAME.match(name):
            raise AzureError("a setting's name is letters, digits and underscores")
        if is_guarded(name) and (confirm or "").strip().lower() != app.split("/")[0].lower():
            raise AzureError("%s is a guarded setting - type the app's name (%s) to confirm"
                             % (name, app.split("/")[0]))
        cur = self.settings(app)
        before = shown(name, cur.get(name)) if name in cur else None
        if delete:
            if name not in cur:
                raise AzureError("%s is not set on %s" % (name, app))
            cur.pop(name)
        else:
            value = "" if value is None else str(value)
            if name.upper() == "DATABASE_URL" and is_test_target(app) and value:
                for other in self.apps():
                    if is_test_target(other["name"]):
                        continue
                    try:
                        if self.settings(other["name"]).get("DATABASE_URL") == value:
                            raise AzureError("that is the database %s uses - a test app or slot must never "
                                             "point at production's database" % other["name"])
                    except AzureError as e:
                        if "must never" in str(e):
                            raise
            cur[name] = value
        self._call("PUT", self._id(app) + "/config/appsettings", {"properties": cur})
        return before

    def restart(self, app):
        self._call("POST", self._id(app) + "/restart")


# The switches the sites actually run on, with what each one does, so the page
# can offer a proper control instead of a text box. A switch is offered on the
# apps that already carry it, and can be added to any app.
SWITCHES = [
    {"name": "DISPATCH_PUSH", "site": "Tickets", "kind": "choice", "choices": ["off", "preview", "on"],
     "help": "Approved batches to the dispatch board: off, preview only, or really written."},
    {"name": "DISPATCH_PUSH_AUTO", "site": "Tickets", "kind": "bool",
     "help": "Send to the board automatically when a batch is fully approved (otherwise by button)."},
    {"name": "OCR_BATCH", "site": "Tickets", "kind": "bool",
     "help": "Read scans through the half-price batch queue (slower). Off = read straight away at full price."},
    {"name": "OCR_MODEL", "site": "Tickets", "kind": "text", "help": "The model that reads tickets."},
    {"name": "OCR_SKIP_SLIPS", "site": "Tickets", "kind": "bool",
     "help": "Skip transcribing printed third-party slips (they are still filed as pictures)."},
    {"name": "READ_OIL", "site": "Tickets", "kind": "bool", "help": "Read crude oil packets."},
    {"name": "AP_MAIL_USER", "site": "AP", "kind": "text", "help": "The main AP mailbox (one address)."},
    {"name": "AP_MAIL_USERS", "site": "AP", "kind": "text",
     "help": "The company AP mailboxes, comma-separated. Each must be in Titan OCR Mailboxes first."},
    {"name": "AP_MAIL_SKIP", "site": "AP", "kind": "text",
     "help": "Emails naming any of these (comma-separated) are left out. Empty = nothing left out."},
    {"name": "AP_MAIL_SINCE", "site": "AP", "kind": "text", "help": "Read mail from this date (YYYY-MM-DD) once."},
    {"name": "AP_POLL_MINUTES", "site": "AP", "kind": "number", "help": "Minutes between mailbox checks."},
    {"name": "AP_AI_READ", "site": "AP", "kind": "choice", "choices": ["on", "off"],
     "help": "Use the AI reader for invoices the rules cannot read."},
    {"name": "AP_TEST_USERS", "site": "AP", "kind": "text", "help": "Who may use the Test area (comma-separated)."},
    {"name": "TANK_READ_FULL_S", "site": "Dispatch", "kind": "number",
     "help": "Seconds between full re-reads of the tank window (3600 = hourly; higher = less database traffic)."},
    {"name": "TANK_API_CACHE_S", "site": "Dispatch", "kind": "number",
     "help": "Seconds the tank board keeps its numbers before asking again."},
    {"name": "PORTAL_ADMINS", "site": "All", "kind": "text",
     "help": "Break-glass admins: always let into every site. Guarded."},
]
