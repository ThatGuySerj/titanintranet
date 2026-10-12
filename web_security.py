"""security-headers-v1 (12 Oct 2026): the browser-side protections every Titan
site sends, and its session cookie's flags. Copied, not packaged, into each
Titan web app (the same as titan_auth.py) - keep the copies the same.

Headers, on every response unless a route set its own:

  Strict-Transport-Security   the browser only ever talks to this site over
                              HTTPS, for a year - a downgrade on hotel wifi is
                              refused. Not includeSubDomains: one subdomain
                              without HTTPS would be locked out.
  X-Frame-Options +           no other website can show these pages inside a
  CSP frame-ancestors         frame of its own (clickjacking). Frames from the
                              site itself - the invoice viewer, the print
                              window - still work.
  CSP base-uri / object-src   an injected <base> tag cannot redirect the page's
                              links, and no plugin content runs.
  X-Content-Type-Options      a file is only ever treated as what it says it is.
  Referrer-Policy             another site sees where a link came from, never
                              the full address (which can carry a batch id).
  Permissions-Policy          no location, microphone or payment API - none of
                              the sites use them.

A full Content-Security-Policy that limits scripts would also need every inline
script in the pages moved or hashed; that is a project of its own, not this.

The session cookie: Secure (HTTPS only), HttpOnly (no script can read it) and
SameSite=Lax (not sent on another site's form posts). Microsoft sign-in comes
back as a plain link (response_mode=query), which Lax allows. COOKIE_SECURE=0
turns Secure off for a local run over plain http.
"""
import os

HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": "frame-ancestors 'self'; base-uri 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), payment=(), usb=()",
}


def install(app):
    secure = (os.environ.get("COOKIE_SECURE") or "1").strip() not in ("0", "false", "no", "off")
    app.config.update(SESSION_COOKIE_SECURE=secure, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax")

    @app.after_request
    def _security_headers(resp):
        for k, v in HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp
    return app
