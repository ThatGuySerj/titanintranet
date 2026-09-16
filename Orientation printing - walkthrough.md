# Orientation packet printing — walkthrough

One person runs orientation. They were opening nine PDFs out of a SharePoint
folder and printing each one, then doing it again for the next new hire. Now
the intranet has a popup that lists the folder, and one button merges the
ticked files into a single PDF so the browser opens one print dialog.

Three files do the work:

| File | What it is |
|------|------------|
| `orientation.py` | reads the SharePoint folder, merges the PDFs |
| `app.py` | `GET /api/orientation`, `POST /api/print-packets` |
| `test_orientation.py` | 33 tests, no network needed |

Merging uses PyMuPDF. The ticket site already installs it for OCR; here it is
in `requirements.txt` for the packet merge alone.

---

## Part A — one Graph permission

The routes read SharePoint with the **same Entra app registration the mail
ingestion already uses**, so `TENANT_ID`, `GRAPH_CLIENT_ID` and
`GRAPH_CLIENT_SECRET` are already set on the server. What is missing is
permission to read the document library.

**Done: `Sites.Read.All` (application) is added and consented.** That is what
the routes use today.

It is broader than this needs — it can read every SharePoint site in the
tenant, not just Company Documents. What keeps the blast radius small is the
code rather than the permission: `ORIENTATION_ROOT` is fixed and every file
name is checked against that folder's real contents, so no request can steer
the route at `C Suite` or `Safety/Training Sheets`.

`Sites.Selected` is the narrow alternative and is also consented on this app,
but it does nothing on its own — it needs a per-site grant, which the portal UI
cannot do (`POST /sites/{siteId}/permissions` from Graph Explorer). If you ever
want the permission to enforce the folder limit instead of trusting the code,
that is the swap: make the site grant, then remove `Sites.Read.All`.

## Part B — nothing else to configure

These all have working defaults and only need setting if something moves:

| Variable | Default |
|----------|---------|
| `SP_HOST` | `netorgft9778845.sharepoint.com` |
| `SP_SITE_PATH` | `sites/CompanyDocuments` |
| `SP_LIBRARY` | `All Company Documents` |
| `ORIENTATION_ROOT` | `HR/Orientation Forms` |
| `SP_DRIVE_ID` | *(looked up by library name)* |
| `ORIENTATION_USERS` | *(empty — see below)* |
| `ORIENTATION_SITE_SLUG` | *(falls back to `HR_SITE_SLUG`, i.e. `titan-hr`)* |
| `SITE_DIR` | `site` |

`SP_LIBRARY` is the library's **URL name**, which is `All Company Documents` —
not `Documents` and not `Shared Documents`. If the folder listing 404s, that is
the first thing to check. Setting `SP_DRIVE_ID` skips two Graph calls per
request; the id is in the error message if you ever want it.

### Who is allowed

Two lists, and either one grants access.

**`ORIENTATION_USERS`** — a comma-separated list of email addresses in the app
settings. This is the one to use while the portal is not deployed:

    ORIENTATION_USERS = hr@tetransports.com, swahl@tetransports.com

Case and stray spaces do not matter. Restart or redeploy for a change to take.

**The portal's access list** — `titan-hr`, the same group as payroll, because
orientation packets are HR material and it tends to be the same person. This
starts working on its own once the portal is up; set `ORIENTATION_SITE_SLUG`
to a slug of its own if orientation and payroll should be separate people.

The two are additive on purpose. `ORIENTATION_USERS` grants access whatever the
portal says, so nobody who can print packets today loses that when the portal
arrives — and there is no window where the feature is ungrantable.

That window was real: `portal_sites` and `portal_access` live in the *portal's*
schema, so before the portal is deployed those tables do not exist,
`auth.may_use()` throws, and it fails closed as designed. Without
`ORIENTATION_USERS` the result was a feature nobody but `PORTAL_ADMINS` could
use and no screen anywhere could grant. A missing table now logs at info and
means "no", rather than erroring and becoming a 503 that reads like an outage.

## Part C — publish the page

The intranet page lives in two places on purpose: the Desktop copy is the one
to edit, `webapp/intranet/` is the one that deploys. Run **`Publish
Intranet.cmd`** in the repo root after every edit, then deploy as usual.

Editing the Desktop copy and wondering why the site did not change is the
whole reason that script exists.

## Part D — intranet.tetransports.com

The intranet has its own domain, served by **this same app** rather than one of
its own. One deployment, one set of secrets, and the packet-printing routes stay
same-origin with the page that calls them — so the browser sends the session
cookie and no CORS is involved.

Both addresses work until you say otherwise, so nothing breaks while DNS and
the certificate come up. `INTRANET_HOST` overrides the hostname if it changes.

**Before the move** (`INTRANET_MOVED` unset):

| Host | `/` | `/intranet/` | `/images/*` |
|------|-----|--------------|-------------|
| `intranet.tetransports.com` | the intranet | the intranet | the logos |
| `tickets.tetransports.com` | ticket tracker | the intranet | 404 |

**After** — set `INTRANET_MOVED=1` in the app settings once the new address is
actually answering:

| Host | `/` | `/intranet/` | `/images/*` |
|------|-----|--------------|-------------|
| `intranet.tetransports.com` | the intranet | 301 → `/` | the logos |
| `tickets.tetransports.com` | ticket tracker | **301 → the new domain** | 404 |

The ticket site then serves no intranet content at all, and there is one
address for the intranet rather than two. A 301 rather than a 404 so an old
bookmark lands on the new site instead of a dead end; change the code to
`abort(404)` in `_intranet_moved()` if you would rather it simply be gone.

It is a switch and not the default on purpose: turning it on before the new
host answers would leave the intranet reachable at neither address.

### Two Web Apps, one repository

`titantickets` and `titanintranet` run the **same code** from the same repo as
two Azure Web Apps on the **same App Service Plan**. Extra apps on a plan cost
nothing — you pay for the plan — and the point of the split is that they
**restart independently**. Before it, renaming a link on the noticeboard
restarted the one process both sites ran in, and the ticket site went down for
the length of a deploy.

Deployment slots would be the textbook answer and would fix ticket-site deploys
too, but slots need Standard and this plan is Basic B1. Two apps is the free
version of the same idea.

They do share the B1's single core. A noticeboard beside the ticket app is not
much load, but heavy OCR on the ticket side is felt here.

**Which workflow runs when**

| Changed | titantickets | titanintranet |
|---------|--------------|---------------|
| `webapp/intranet/**`, `intranet_access.py` | — | deploys |
| `app.py`, `titan_auth.py`, `orientation.py`, `requirements.txt` | deploys | deploys |
| `render.py`, `worker.py`, `Ticket Tracker.html` | deploys | deploys |
| any `.md` | — | — |

Intranet-only changes never touch the ticket site, which is the whole point.
Shared code deploys both, deliberately: an intranet left behind on old shared
code is a harder fault to find than one extra deploy. Both workflows also have
**Run workflow** in the Actions tab if you want to push one by hand.

### Standing the second app up

1. **Create the Web App** — `titanintranet`, Linux, **Python 3.12**, same
   Resource Group, and **the existing App Service Plan** (picking the existing
   plan is what makes it free; a new plan would double the bill).
2. **Startup command** — Settings → Configuration → General settings:
   ```
   gunicorn --chdir webapp --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app
   ```
3. **App settings** — copy them from `titantickets`, then:
   - add **`RUN_WORKER=0`** — the OCR poller must not run here. It is *safe* if
     it does, because the run is behind a Postgres advisory lock, but it is
     pointless work on a core both sites share.
   - add **`INTRANET_HOST=intranet.tetransports.com`** (or leave it; that is
     already the default).
   - `MAIL_USER`, `MAIL_FOLDER`, `OCR_BATCH` and `OCR_MODEL` are not needed
     here. Harmless if copied, since nothing reads them with the worker off.
4. **Move the domain** — add `intranet.tetransports.com` as a custom domain on
   **titanintranet**, create its managed certificate, then remove the domain
   from titantickets. The CNAME target changes to
   `titanintranet.azurewebsites.net`, and a new `asuid.intranet` TXT value.
5. **On titantickets, set `INTRANET_MOVED=1`.** Now `/intranet` there 301s to
   the new address and the ticket app serves no intranet content at all.
6. **GitHub secret** — download the new app's publish profile and add it as
   `AZUREAPPSERVICE_PUBLISHPROFILE_TITANINTRANET`.

Both apps talk to the same database, so groups, rules and everything else are
shared. `intranet.tetransports.com/auth/callback` is already registered in
Entra from the earlier step and does not change.

### Setting it up

1. **DNS** — a CNAME `intranet` → `titantickets.azurewebsites.net`, plus the
   `asuid.intranet` TXT record Azure shows you when you add the domain.
2. **Azure** — titantickets → Custom domains → Add custom domain →
   `intranet.tetransports.com` → validate → add. Then create a free **App
   Service Managed Certificate** for it and bind it.
3. **Entra** — add `https://intranet.tetransports.com/auth/callback` to the app
   registration's redirect URIs, alongside the tickets one.
4. Deploy.

**Sign-in needed no code change.** `titan_auth.redirect_uri()` builds the
callback from the request host whenever `AUTH_REDIRECT` is unset, and it is
unset on this app. Setting it would pin every sign-in to one host and send
anybody arriving on the other into a redirect loop — so leave it alone.

Sessions are per-host, because the cookie is host-only. Somebody signed in on
tickets will still do a silent round trip through Microsoft the first time they
open the intranet — about a second, nothing shown. Setting `SSO_SECRET` and
`SSO_COOKIE_DOMAIN=.tetransports.com` would make it instant, and that is the
same switch every other Titan site uses.

### One thing that does not move

The bookmarks bar inside the page keeps its data in `localStorage`, which is
scoped to the origin. Bookmarks saved at `tickets.tetransports.com/intranet/`
will **not** appear at `intranet.tetransports.com` — they never left that
browser, so there is nothing to migrate. Worth telling anyone who has been
using it before they wonder where their stars went.

That is a reason to tell people before flipping `INTRANET_MOVED`, not a reason
to delay it — the bookmarks do not survive the move whenever it happens.

---

## How it behaves

**`GET /api/orientation?folder=Energy`**

```json
{ "folders": ["Energy", "Kimberley"],
  "folder":  "Energy",
  "files": [ { "name": "SSE Packet.pdf", "size": 3859028, "mergeable": true } ] }
```

`folders` is the sub-folders of the orientation root — that is the company
dropdown, so **adding a company is making a folder**. `mergeable` is true for
PDFs and for anything Graph will convert (Word, Excel, PowerPoint, RTF, ODF);
the page unticks and flags anything else rather than letting the print quietly
come out short.

**`POST /api/print-packets`**

```json
{ "folder": "Energy", "packets": ["SSE Packet.pdf"], "copies": 12,
  "duplex": true }
```

`duplex` defaults to **true** when the key is absent — see *Front and back*.

Answers `application/pdf` with the merged file, or JSON with an `error`. The
page treats any non-PDF response as a failure and shows the `error` sentence,
so a message written here is a message the person reads.

Status codes are deliberate: **501** the server is not configured, **502**
SharePoint or the folder said no, **403** signed in but not on the list, **401**
sign-in ran out. Only a genuine crash is a 500.

### Names, not paths

The page sends bare file names. `orientation.py` refuses anything containing a
separator, a `..`, a leading dot or a null, and then checks every name against
what the folder actually holds before downloading a byte. A path arriving here
did not come from the page.

That last check earns its keep on the ordinary case too: if a packet is renamed
in SharePoint between the popup listing it and Print being pressed, HR gets
told which file went missing rather than a set that is quietly one packet short.

### Front and back

These get printed double-sided, so every packet has to start on the front of a
sheet. `merge()` pads any packet with an odd page count with one blank page.

With three packets of 2, 3 and 1 pages:

| | pages | packets start on |
|---|---|---|
| padding on *(default)* | 8 | 1, 3, 7 — all fronts |
| padding off | 6 | 1, 3, **6** — the third is on the back of sheet 3 |

The padding also runs after the **last** packet, which is the part that is easy
to miss: an odd total puts the second collated copy on the back of the first
copy's last sheet. Same fault, one level up, and it only shows itself once
somebody prints twelve.

A blank page is sized to match the sheet it backs onto rather than assumed to
be Letter, so a landscape or legal packet does not get a portrait blank and
leave the printer to scale or refuse the stack.

The popup has a **Front and back** tick box, on by default, sending
`"duplex": true`. Turning it off is for single-sided printing, where the
padding would just waste a sheet per odd packet.

The response carries `X-Packet-Pages` and `X-Packet-Blanks`, and the popup uses
them to say "3 blank pages added so every packet starts on a new sheet". A
blank sheet in the middle of a stack reads as a misprint otherwise, and the
cure for that is a sentence rather than a different PDF.

### Copies

`copies` is written into the PDF's `/ViewerPreferences /NumCopies`, not by
repeating pages. A full Energy set is about 37 MB; twelve sets of repeated
pages would be roughly 450 MB — slow to build and enough to choke a spooler.
Acrobat reads `/NumCopies` and fills the dialog in, browser viewers ignore it,
so the page also tells the person the number to type. The printer does the
collating, which is what printers are good at.

### The download redirect

Graph answers a `/content` request with a 302 to a pre-authenticated storage
URL. That second request must **not** carry the bearer token — the storage host
rejects a request holding both its own signature and an `Authorization` header
— and urllib keeps headers we set across a redirect. So `_bytes()` catches the
redirect and re-issues it clean, using a **private opener**. An
`install_opener()` here would have swapped the default opener out from under
`graph.py` and everything else in the process.

---

## Tests

```
cd webapp
python -m pytest test_orientation.py -q        # 25 passed
```

No network and no SharePoint: the Graph client is replaced with a folder tree
in memory. The PDFs in the fixtures are real, built with PyMuPDF, so the merge
is a genuine merge and the page-count assertions mean something.

What they actually pin down: that print order follows folder order, that a
renamed file is an error rather than a short set, that twelve copies produces
three pages and not thirty-six, that a path is refused instead of normalised,
and that `NotConfigured` stays a subclass of `OrientationError` — if that ever
changes, an unconfigured server starts answering 500 and reads like a crash.
