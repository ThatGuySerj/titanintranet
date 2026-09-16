# Titan Enterprises intranet

`intranet.tetransports.com` — the company noticeboard. Its own repository, its
own Azure Web App, deployed on its own schedule. Nothing here can restart the
ticket site, and nothing there can restart this.

```
Intranet/
├─ app.py                  the whole site
├─ intranet_access.py      who sees what
├─ orientation.py          reads the packet folder, merges the PDFs
├─ titan_auth.py           COPY of the shared sign-in module
├─ db.py                   a connection to the shared database
├─ site/
│  ├─ index.html           the page — no content of its own
│  ├─ config.json          WHAT IS ON THE INTRANET. Edit this.
│  └─ images/
├─ test_intranet_access.py 28 tests
├─ test_orientation.py     33 tests
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

## Changing things

**What is on the intranet** → `site/config.json`. One file, one copy. Cards,
documents, rail links, alerts, the SharePoint folders. Push and it deploys.

**Who sees what** → the **Access** screen at `/access`, signed in as an
administrator. No deploy: it is database rows.

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
python -m pytest -q          # 61 passed
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

`MAIL_*`, `OCR_*` and `RUN_WORKER` belong to the ticket site. Nothing here
reads them — there is no worker in this app to turn off.

Startup command on Azure:

```
gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app
```

No `--chdir`: `app.py` is at the root of this repository, unlike the ticket
one where it sits under `webapp/`.

## What it shares with the ticket site

Only the database and the Entra app registration. Three tables are this site's
own — `intranet_group`, `intranet_member`, `intranet_rule` — and it creates
them itself on boot rather than through the ticket site's `schema.sql`, so a
permissions change never takes a lock on a table reviewers are filing tickets
into.

Sessions are per-host, so signing in here is separate from signing in on
tickets. It is a silent round trip through Microsoft, about a second with
nothing shown. Setting `SSO_SECRET` and `SSO_COOKIE_DOMAIN=.tetransports.com`
on both sites would make it instant.

## The two walkthroughs

- `Intranet permissions - walkthrough.md` — groups, rules, how filtering works
- `Orientation printing - walkthrough.md` — the packet popup and the merge
