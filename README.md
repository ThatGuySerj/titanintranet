# Titan Enterprises intranet

`intranet.tetransports.com` — the company noticeboard. Its own repository, its
own Azure Web App, deployed on its own schedule. Nothing here can restart the
ticket site, and nothing there can restart this.

```
Intranet/
├─ app.py                  the whole site
├─ intranet_access.py      who sees what
├─ orientation.py          reads the packet folder, merges the PDFs
├─ fileplan.py             the proposed filing structure, as data
├─ sitemap.py              reads AND WRITES the Site Mapping folder
├─ titan_auth.py           COPY of the shared sign-in module
├─ db.py                   a connection to the shared database
├─ site/
│  ├─ index.html           the page — no content of its own
│  ├─ fileplan.html        /fileplan — no content of its own either
│  ├─ config.json          WHAT IS ON THE INTRANET. Edit this.
│  └─ images/
├─ test_intranet_access.py 28 tests
├─ test_orientation.py     41 tests
├─ test_fileplan.py        31 tests
├─ test_sitemap.py         76 tests
└─ .github/workflows/main_titanintranet.yml
```

## Why it is separate

It lived inside the ticket repository for a fortnight. One repository meant one
Azure Web App, one process, and one restart — so renaming a link on the
noticeboard took the site people file tickets in down with it for the length of
a deploy.

Deployment slots would fix that properly, but they need Standard and the plan is
Basic B1. Two Web Apps on the same plan cost nothing extra and restart
independently, which is the same benefit for the money already being spent.

`titan_auth.py` is a **copy**, which is how every Titan site carries it — the
portal's README explains why: separate repositories deploying on separate
schedules would otherwise wait on a package release for a sign-in fix.
`/healthz` prints its version so one site being behind the others is visible
rather than something you find out about.

## Why a deploy takes as long as it does

Almost none of it is the runner. What gets sent to Azure is the source — about
700 KB, 25 files. What costs the minutes happens afterwards, on the web app:
`SCM_DO_BUILD_DURING_DEPLOYMENT=true` makes Azure run `pip install` over
`requirements.txt` **on the instance**, and that is 110 MB of wheels (PyMuPDF
is most of it) fetched and unpacked on one core of a Basic B1 that the ticket
site is also using. Then the container restarts and takes a cold start to
answer. The deploy step waits for all of it, so renaming a link costs what a
rewrite costs.

The workflow no longer pays for anything twice — one job, no artifact round
trip, pip cached, the test virtualenv in `/tmp` so it cannot be swept into the
package. That is the runner side finished. The rest is Azure's, and there are
only two real ways to spend less of it:

**Build on the runner instead.** Create the virtualenv in the workspace, ship
it, and set `SCM_DO_BUILD_DURING_DEPLOYMENT=false`. The build moves from one
shared B1 core to a fast runner, and the app only unpacks. The cost is a 110 MB
upload each deploy instead of 700 KB, and a dependency on the runner's wheels
being right for App Service's container — they are both x86-64 manylinux, so
they are, until one day they are not. The health check at the end of the
workflow is what would catch that.

**Stop sharing the core.** B2, or move one of the two sites to its own plan.
This is the honest fix and it is the one that costs money. It also fixes the
occasional OneDeploy 503, which is the same squeeze wearing a different hat.

Neither is worth doing for a noticeboard that changes twice a week. Both are
worth doing the week the intranet starts changing twice a day.

## Changing things

**What is on the intranet** → `site/config.json`. One file, one copy. Cards,
documents, rail links, alerts, the SharePoint folders. Push and it deploys.

**Who sees what** → the **Access** screen at `/access`, signed in as an
administrator. No deploy: it is database rows.

**The filing system** → `/fileplan`, the **folders** tab. That is the real
`Site Mapping` folder in SharePoint: new folders, renames, moves, uploads and
deletes all land there. `sitemap.py` does the talking and confines every path
to `MAP_ROOT`; `Filing system editor - walkthrough.md` has the Entra permission
it needs and what that permission is worth watching for.

**The filing system plan** → `fileplan.py`. `/fileplan` is the proposed
SharePoint structure made walkable, for arguing with before it is built. Every
number the page shows is counted from the tree in that file rather than quoted
from the document's prose, so the page cannot claim one thing and draw another.
It is gated on the rail link's own key, so hiding **Filing System Plan** on the
Access screen shuts the page itself rather than only the link to it.

**How it looks** → `site/index.html`. It carries no content; the server writes
the configuration into it between two markers, filtered to whoever is signed in.

Opening `index.html` off the disk shows a note rather than the intranet, because
nothing has filled it in. That is the cost of the filtering being real: while
the configuration sat in the page, hiding a card in JavaScript was a curtain
and not a lock.

## Running it here

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set SECRET_KEY=dev
set DATABASE_URL=...        the same one the ticket site uses
python app.py               http://localhost:8001
```

Tests need neither a database nor the network:

```
python -m pytest -q          # 178 passed
```

## Settings

Copy from the ticket app: `DATABASE_URL`, `SECRET_KEY`, `TENANT_ID`,
`AUTH_CLIENT_ID` (and its secret), `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`,
`PORTAL_ADMINS`, `OFFICE_PASSCODE`.

This site's own:

| Variable | Default | What it does |
|----------|---------|--------------|
| `SITE_DIR` | `site` | where the page and config live |
| `ORIENTATION_USERS` | — | who may print packets, comma separated |
| `ORIENTATION_ROOT` | `HR/Orientation Forms` | the packet folder |
| `SP_SITE_PATH` | `sites/CompanyDocuments` | the SharePoint site |
| `SP_LIBRARY` | `All Company Documents` | the library's URL name |
| `MAP_ROOT` | `Site Mapping` | the folder the filing system editor may change |

`MAIL_*`, `OCR_*` and `RUN_WORKER` belong to the ticket site. Nothing here
reads them — there is no worker in this app to turn off.

Startup command on Azure:

```
gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app
```

No `--chdir`: `app.py` is at the root of this repository, unlike the ticket
one where it sits under `webapp/`.

## What it shares with the ticket site

Only the database and the Entra app registration. Four tables are this site's
own — `intranet_group`, `intranet_member`, `intranet_rule` and
`intranet_map_log` — and it creates
them itself on boot rather than through the ticket site's `schema.sql`, so a
permissions change never takes a lock on a table reviewers are filing tickets
into.

Sessions are per-host, so signing in here is separate from signing in on
tickets. It is a silent round trip through Microsoft, about a second with
nothing shown. Setting `SSO_SECRET` and `SSO_COOKIE_DOMAIN=.tetransports.com`
on both sites would make it instant.

## The walkthroughs

- `Intranet permissions - walkthrough.md` — groups, rules, how filtering works
- `Orientation printing - walkthrough.md` — the packet popup and the merge
- `Filing system editor - walkthrough.md` — the live SharePoint folder, the
  permission it needs, and who can change what
