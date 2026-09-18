# The filing system editor — walkthrough

`/fileplan` used to be a drawing of a proposed folder structure. It now has two
tabs that matter:

| Tab | What it is |
|-----|------------|
| **The folders** | the real `Site Mapping` folder in SharePoint. Changes here are changes there. |
| **The plan** | still a proposal — the 732-folder structure from TGC-SYS-EFILE-2026-01 |

The left-hand panel of the live tab builds branches of the plan into the real
folder, one master folder at a time.

---

## Part A — the one thing that must be done in Entra

**Nothing below works until this is granted.** Until then every write answers
`403` with a message saying so, and browsing still works.

1. Entra admin centre → **App registrations** → the app whose id is in
   `GRAPH_CLIENT_ID` (the same one the orientation printing and the mail
   ingestion use).
2. **API permissions → Add a permission → Microsoft Graph → Application
   permissions**.
3. Tick **`Sites.ReadWrite.All`**. Add it.
4. **Grant admin consent** for the tenant. The row has to end up with a green
   tick under Status — a permission that is added but not consented does
   nothing at all.

No restart is needed. The app asks for a fresh token every hour and the new
permission is in the next one; if you are impatient, restart the web app.

### What that permission actually gives away

`Sites.ReadWrite.All` is application-level write access to **every SharePoint
site in the tenant** — C Suite, the signed personnel records in
`Safety/Training Sheets`, all of it. It is not scoped to Company Documents and
it cannot be, because it is a tenant-wide permission by design.

What keeps this app inside one folder is **code, not Microsoft**:
`sitemap.Tree._full()` resolves every path that arrives from a browser against
`MAP_ROOT` and refuses anything that lands outside it. Every read and every
write goes through that one function. It has thirty-odd tests of its own,
including one that fails if a future method stops calling it.

That is a real safeguard and it is worth knowing it is the only one. The
narrow alternative — `Sites.Selected` with a write grant on the Company
Documents site alone, which is already consented on this app — would let
Microsoft enforce the boundary instead of us. It needs one `POST
/sites/{siteId}/permissions` call from Graph Explorer. The swap is a ten-minute
job if you ever want it; nothing in the code changes.

---

## Part B — who can do what

**Anybody signed in can add, rename, move, upload and delete.** That was the
decision. It means the usual protection — only two people can break it — is
not there, so two other things carry the weight:

**Everything is written down.** `intranet_map_log` records the email, the
action, the path and the time of every change. The right-hand panel of the live
tab shows the last hundred. This matters more than it looks: Graph writes are
made with the *app's* identity, so SharePoint's own version history will say
the app renamed a folder and never who asked it to. The intranet's log is the
only place a person's name is attached to a change.

**A delete that cannot be logged does not happen.** If Postgres is unreachable,
new folders, renames, moves and uploads still work and the failure to log is a
warning in the Azure log stream. Deleting is refused outright, with a message
saying to do it in SharePoint instead, where the person's own name goes on it.
An unattributable delete is the one thing this will not do.

**Deleting goes to the site's recycle bin**, where SharePoint keeps it for 93
days, and a second-stage bin holds it after that. Nothing here destroys a file
outright. The confirmation says how many items are inside a folder before it
goes.

If this turns out to be too loose in practice, the switch is one line in
`map_allowed()` in `app.py` — the group machinery is already there and the
Access screen already has an administrators group.

---

## Part C — how it behaves

**Names on screen are not the names on disk.** SharePoint holds
`00-09-01_Letterhead-and-Brand-Assets`, because the numbering is what sorts the
folder and the convention says no spaces. The intranet shows **Letterhead and
Brand Assets**, with the real name underneath it in small type. Nothing is
hidden and nothing is renamed — you get the readable one to work with and the
literal one to quote in an email.

The list is also sorted by those numbers **as numbers**. SharePoint sorts them
as text, which puts 100 between 10 and 110; every numbered filing system hits
that eventually and everybody blames the numbering rather than the sort.

**Nothing moves while a folder loads.** The list dims where it stands and a
two-pixel bar runs along the top edge of the pane. No element changes size, so
walking into ten folders in a row does not shuffle the page under the pointer.
Anything that needs words — "Made X", an error — appears as a small panel in
the bottom corner, over the layout rather than in it.

**Browsing.** The middle pane is the current folder, folders first. Clicking a
folder opens it; clicking a file opens it in SharePoint in a new tab. The
breadcrumb walks back up. The filter box narrows the folder you are in — it is
not a search across the whole tree, because that would be a Graph search call
per keystroke.

**New folder** makes one where you are standing. **Upload** takes a file up to
4 MB, and so does dragging one onto the list. Anything bigger goes into
SharePoint directly — the browser would be posting it through a Basic B1 web
app that holds the whole thing in memory, and the Open in SharePoint link is
one click from every folder.

**Moving** is cut and paste, deliberately: press **move** on a row, walk to the
folder it belongs in, press **Paste**. Drag-and-drop across a tree that is
being read a folder at a time is a worse experience than it sounds, and this
one cannot drop a folder into itself by accident (the server refuses that
anyway).

**Names** are checked here before SharePoint sees them, so you get "SharePoint
will not accept : in a name" rather than a 400 from Graph. The rules are
SharePoint's own: no `" * : < > ? / \ |`, nothing starting with `.` or `~`,
nothing ending in a full stop, no Windows reserved names, 255 characters.

---

## Part D — building the plan into SharePoint

The bottom-left panel lists the eighteen master folders. A folder already in
Site Mapping shows a tick; the rest show a plus. Clicking one creates that
master folder and everything under it — 40-odd folders, a few seconds. **Build
the N that are missing** walks the lot.

It is done one master folder at a time on purpose. The whole plan is 732
folders and Graph takes one request per folder: in a single request it would
sit for minutes and gunicorn would cut it off at 120 seconds with half the tree
made and no way to tell which half. Eighteen calls finish in a few seconds each
and the page shows progress.

**Re-running is safe.** Anything already there is left alone, so a seeding run
that failed halfway can simply be run again. That is also how the tick appears:
the panel compares the plan against what is really in the folder every time it
reloads.

---

## Part E — when Site Mapping stops being a sandbox

The whole structure lives under `Site Mapping` while its shape is being argued
about. When it graduates and becomes the library itself, set the app setting:

```
MAP_ROOT =            (empty)
```

The fence widens with it — `_full()` uses the same setting — and the editor is
then working on the whole of All Company Documents. There is a test for that
case. **Think before doing it**, because at that point anybody signed in can
rename `Safety` and delete `C Suite`, and the only record is the intranet's own
log. That is the week to move editing behind a group.

---

## Settings

| Variable | Default | What it does |
|----------|---------|--------------|
| `MAP_ROOT` | `Site Mapping` | the folder the editor is confined to |

Everything else it needs — `TENANT_ID`, `GRAPH_CLIENT_ID`,
`GRAPH_CLIENT_SECRET`, `SP_SITE_PATH`, `SP_LIBRARY` — it shares with the
orientation printing and already has.

---

## Tests

```
python -m pytest test_sitemap.py -q        # 76 passed
```

No network and no SharePoint. Most of them are about the fence: every escape
pattern is tried against every write method, and one test fails if a method is
ever added that builds a path without consulting the guard. The rest cover the
name rules, the upload limit, and that seeding makes parents before children —
Graph cannot create a folder inside one that does not exist yet, so the walk
order is not a detail.

The routes are tested for the two answers that matter on a server with no Graph
credentials at all: an escape is `403` before anything reaches SharePoint, and
a bad name is `400` with the reason in it.

---

## Still to come

The rest of what was asked for, in order:

1. Department names on the front page linking straight to their folder
2. The four sections — Static, Most opened, Recently opened, Favourites — with
   show more and show all
3. The welcome screen: message from the owner, employee of the month, the
   noticeboard things, with the files below it — as its own tab first, so it
   can be looked over before it becomes the front of the site

"Most opened" and "recently opened" need the intranet to start recording opens,
which is a fifth table and a decision about whether "most opened" means yours
or everybody's. It reads as: **recently opened** is yours, **most opened** is
the company's, over the last month or so.
