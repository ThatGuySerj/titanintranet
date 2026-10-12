# The admin site: intranet.tetransports.com/admin

One page for every Titan site, which works on a computer or a phone. Only the people in `ADMIN_SITE_USERS` can open it. Until that setting exists, that means swahl@ and dboothe@. Everyone else gets "This page is for the Titan admins", including the intranet's own admins and `PORTAL_ADMINS`.

| Section | What you can see | What you can do |
|---|---|---|
| Overview | Each site up or down, the ticket and AP mailboxes, the OCR queue, the tray, tank readings, the last dispatch-board send, database size, stuck connections | Check the ticket mail and run the queue now |
| Access | Who can open each site (the list every site checks at sign-in), portal admins, intranet groups | Give and remove access, add a site, turn a site off, open a site to everyone (you type the site's short name to confirm), edit intranet groups |
| Scans & mail | OCR jobs, the ticket worker, scans in the tray and discarded ones, each AP mailbox, AP emails that failed or were left out | Retry, run or cancel a job, put a discarded scan back in the tray, re-read an AP mailbox from a time, have one failed email read again |
| Restore | The AP backups taken before the clean-outs, voided AP invoices | Put a backup back (you type `restore`; anything already there is skipped), reopen a voided invoice |
| Database | Connections, schema and table sizes, the queries moving the most data | End one stuck connection |
| Activity | Recent changes across the sites, and everything done on this page | — |

The page is laid out to be read at a glance. Overview opens with one line, either "Everything is running" or a short list of what needs attention, and each item links to the section where it gets fixed. The technical parts are folded under "Show …": the database queries and sizes, and finished OCR jobs.

Every change made on the page is recorded in `intranet_admin_log`, with who made it and when.

## 1. Put it up

The intranet folder also has your own unfinished file-plan changes. Commit only the admin files:

```powershell
cd "$env:USERPROFILE\OneDrive - tetransports.com\Desktop\Intranet"
git add admin.py admin_page.py test_admin.py app.py "Admin site - walkthrough.md"
git commit -m "Admin site at /admin"
git push
```

The push deploys to `titanintranet` once the tests pass. Then open https://intranet.tetransports.com/admin.

Everything works straight away. There is no Settings section: Azure settings are changed in the Azure portal, and the page has no login to Azure at all.

## Settings on the intranet app

| Setting | Default | What it does |
|---|---|---|
| `ADMIN_SITE_USERS` | swahl@, dboothe@ | Who can open /admin, comma-separated. Set it to blank and nobody can. |
| `ADMIN_HEALTH_URLS` | the four sites | `Name=https://…,Name=https://…` replaces the list of sites Overview checks. |
| `ADMIN_TICKETS_SCHEMA`, `ADMIN_AP_SCHEMA`, `ADMIN_DISPATCH_SCHEMA` | ocr, ap, dispatch | The database schemas the page reads. |

The page uses the intranet's own database login. If that login can't read a schema, only that section says so and the rest of the page still works.
