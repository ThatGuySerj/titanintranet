# The admin site: intranet.tetransports.com/admin

One page for every Titan site, which works on a computer or a phone. Only the people in `ADMIN_SITE_USERS` can open it. Until that setting exists, that means swahl@ and dboothe@. Everyone else gets "This page is for the Titan admins", including the intranet's own admins and `PORTAL_ADMINS`.

| Section | What you can see | What you can do |
|---|---|---|
| Overview | Each site up or down, the ticket and AP mailboxes, the OCR queue, the tray, tank readings, the last dispatch-board send, database size, stuck connections | Check the ticket mail and run the queue now |
| Access | Who can open each site (the list every site checks at sign-in), portal admins, intranet groups | Give and remove access, add a site, turn a site off, open a site to everyone (you type the site's short name to confirm), edit intranet groups |
| Settings | Each web app's Azure settings, with plain controls for the switches that matter | Change, add or delete a setting, restart an app |
| Mail & OCR | OCR jobs, the ticket worker, scans in the tray and discarded ones, each AP mailbox, AP emails that failed or were left out | Retry, run or cancel a job, put a discarded scan back in the tray, re-read an AP mailbox from a time, have one failed email read again |
| Restore | The AP backups taken before the clean-outs, voided AP invoices | Put a backup back (you type `restore`; anything already there is skipped), reopen a voided invoice |
| Database | Connections, schema and table sizes, the queries moving the most data | End one stuck connection |
| Activity | Recent changes across the sites, and everything done on this page | — |

Every change made on the page is recorded in `intranet_admin_log`, with who made it and when.

## 1. Put it up

The intranet folder also has your own unfinished file-plan changes. Commit only the admin files:

```powershell
cd "$env:USERPROFILE\OneDrive - tetransports.com\Desktop\Intranet"
git add admin.py admin_page.py azure_admin.py test_admin.py app.py "Admin site - walkthrough.md"
git commit -m "Admin site at /admin"
git push
```

The push deploys to `titanintranet` once the tests pass. Then open https://intranet.tetransports.com/admin.

Everything except **Settings** works straight away.

## 2. Connect Settings to Azure (one time)

The Settings section talks to Azure using its own login, a service principal. Make it in the Azure portal:

1. **Microsoft Entra ID → App registrations → New registration**. Name it `Titan admin site`, leave the defaults and register it. Copy the **Application (client) ID**.
2. On that registration, go to **Certificates & secrets → New client secret**. Choose 24 months and copy the **Value** straight away; it is shown only once. Put the expiry date in your calendar.
3. Open the **resource group** the web apps are in (titantickets, titan-ap, titan-dispatch, titanintranet). Go to **Access control (IAM) → Add role assignment**, pick **Website Contributor**, then **Members → Select members** and choose `Titan admin site`. Assign it.
4. Copy the **Subscription ID** from the resource group's Overview page.
5. On the **titanintranet** web app, go to **Settings → Environment variables** and add:

   | Name | Value |
   |---|---|
   | `ADMIN_AZ_CLIENT_ID` | the client ID from step 1 |
   | `ADMIN_AZ_CLIENT_SECRET` | the secret value from step 2 |
   | `ADMIN_AZ_SUBSCRIPTION` | the subscription ID from step 4 |

   `TENANT_ID` is already there for sign-in. Apply the changes; the intranet restarts.

If you'd rather use the command line, steps 1–4 can be done in one command (`az login` first):

```powershell
az ad sp create-for-rbac --name "Titan admin site" --role "Website Contributor" --scopes /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

It prints `appId` (the client ID), `password` (the secret) and `tenant`.

## How the Settings section protects you

- **Secrets never reach your phone.** Any setting whose name says key, secret, password, token or connection, and any value with a password inside a URL, shows only as "set, 64 characters". You can type a new value over it, but nobody can read it back from the page.
- **Guarded settings** need the app's name typed before they change. These are the database, sign-in, the session key, the site's short name, `PORTAL_ADMINS`, the mail and storage keys, and anything starting `WEBSITE_` or `SCM_`.
- **A test app or staging slot can never be pointed at production's database.** The page compares the value against the production apps' setting and refuses a match.
- **Every change restarts that app**, for about 30 seconds; Azure does this itself. Restarting by hand also needs the app's name typed.
- **Changes are read, changed, then written.** Azure replaces the whole list on every save, so each save reads the current list first and changes only the one setting.

## Settings on the intranet app

| Setting | Default | What it does |
|---|---|---|
| `ADMIN_SITE_USERS` | swahl@, dboothe@ | Who can open /admin, comma-separated. Set it to blank and nobody can. |
| `ADMIN_AZ_CLIENT_ID`, `ADMIN_AZ_CLIENT_SECRET`, `ADMIN_AZ_SUBSCRIPTION` | — | The Azure login for the Settings section (step 2 above). |
| `ADMIN_HEALTH_URLS` | the four sites | `Name=https://…,Name=https://…` replaces the list of sites Overview checks. |
| `ADMIN_TICKETS_SCHEMA`, `ADMIN_AP_SCHEMA`, `ADMIN_DISPATCH_SCHEMA` | ocr, ap, dispatch | The database schemas the page reads. |

The page uses the intranet's own database login. If that login can't read a schema, only that section says so and the rest of the page still works.
