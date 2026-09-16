# Intranet permissions — walkthrough

Everyone with a Titan account can open the intranet. Groups decide how much of
it they see. The Access screen is at **`/access`** on the intranet, and only
administrators can open it.

| File | What it is |
|------|------------|
| `intranet_access.py` | the rules, the tables, and the filtering |
| `app.py` | the Access screen and the per-person page |
| `test_intranet_access.py` | 28 tests, no database needed |
| `site/config.json` | **what is on the intranet** — the page has no content of its own any more |

---

## The rule

> An item with **no** rule is visible to **everyone**.
> An item **with** a rule is visible only to those groups.

So the default is open and restricting something is a deliberate act. A new
driver is useful on day one without anybody deciding anything.

Cards and documents are restricted separately, and that is the point of having
both:

- a rule on a **card** hides the card and everything in it;
- a rule on a **document** hides just that row.

That combination is what handles the HR case. Leave the HR card open and
restrict the sensitive rows inside it: everybody sees the HR card carrying the
three documents everybody needs, HR sees all sixteen. A card whose every row is
hidden disappears entirely — hiding the rows and then leaving a heading that
names the category is the worst of both.

Administrators see everything, always. Somebody in no group sees everything
that has not been restricted.

## Why this is server-side

The configuration used to live in the page. Hiding a card in JavaScript would
have been a curtain and not a lock: View Source and there were all 149 document
names and every SharePoint folder path — including
`IT and Infrastructure/Termed Employee Data Recovered/Yvonne Recovered/`, which
gives something away by its name alone.

So `config.json` is filtered here and written into the page between two
markers. **A person's copy of the page contains only what that person may
see** — the hidden names are not in the HTML at all. There is a test that
checks exactly that, because it is the whole point and it would be easy to
regress into a CSS rule.

SharePoint still protects the files themselves. Someone who guesses a URL is
refused by SharePoint, not by us. This controls what people are shown, and what
the shape of the library gives away.

## What changed about editing

**To change what is on the intranet, edit `site/config.json`.** The page
no longer carries its own content — it has `var TITAN = null` between the
markers and the server fills it in.

The consequence: opening the HTML file off the disk no longer shows the
intranet, because nothing has filled it in. It says so rather than appearing
broken. Use the real address.

There is one copy of it now, in this repository. The old `Publish Intranet.cmd`
that kept two folders in step is gone with the split.

## Using the Access screen

**Groups** — people go in groups, groups are what sections are opened to.
Six are seeded: Everyone, Office, Drivers, HR, Safety, Administrators. Add your
own; `admins` cannot be deleted. Deleting a group also deletes every rule that
used it, so a section restricted only to that group goes back to being open.

**People** — one row each, a tick box per group, Save. Or paste a list of
addresses into the box at the bottom and put them all in the same groups at
once, which is how it actually happens when four drivers start together.

**What each section shows** — one block per rail group, department, yard,
folder, and the packet popup. Tick nothing for everyone; tick groups to
restrict. Each block has a **`▸ 16 documents`** expander for the per-document
controls, shut by default so the screen is readable; it opens by itself on any
section that already has restrictions inside it.

Each block saves on its own. Saving rewrites every key in that block including
the unticked ones — that is how a rule gets **removed**, and why unticking
everything puts a section back to "everyone".

## Administrators

Either is enough:

- membership of the `admins` group, or
- the `PORTAL_ADMINS` app setting — the same break-glass list the other Titan
  sites use, so a database problem cannot lock out the person who has to fix it.

## How it fails

Deliberately, and open.

If the database is unreachable, `groups_for` returns no groups and `all_rules`
returns no rules. With the open-by-default rule that means people see
everything unrestricted and nothing that is restricted — the intranet behaves
as it did before any of this existed. For a company noticeboard that is the
right way to fail; the alternative is everybody locked out of the holiday form
because Postgres hiccuped.

The tables are created on boot next to `db.init`, not in `schema.sql`, so a
permissions change never takes a lock on a table reviewers are filing tickets
into.

## Caching

The page is `Cache-Control: no-store, private` with `Vary: Cookie`. It is a
different document for every person now, and a shared cache handing one
person's copy to another would be a leak rather than a stale page.

`config.json` is parsed once per worker and re-read when its mtime changes.
Filtering copies rather than mutating, so the cached parse is never touched —
there is a test for that too.
