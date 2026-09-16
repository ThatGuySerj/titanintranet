# Deploying the intranet the first time

Nine steps, in this order. The order matters in one place: **the new site has to
be working before the domain moves to it**, because `intranet.tetransports.com`
currently points at `titantickets` and a domain can only be on one Web App at a
time.

Nothing here touches the ticket site until step 9.

---

## The app's real address

```
https://titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net
```

Azure issues regional hostnames with a hash in them now. The short
`titanintranet.azurewebsites.net` does not resolve. Anywhere below that wants
this address, it means this one — **Overview → Default domain** in the portal
is the authority if it ever changes.

## 1. Make this folder a repository

In a terminal, in `Desktop\Intranet`:

```
git init -b main
git add -A
git commit -m "The intranet, split out of the ticket repository"
```

## 2. Put it on GitHub

Make a new **private** repository called `titan-intranet` — no README, no
.gitignore, GitHub's blank one. Then:

```
git remote add origin https://github.com/ThatGuySerj/titan-intranet.git
git push -u origin main
```

GitHub Desktop does the same job if you would rather: *Add → Add Existing
Repository*, point it here, then *Publish repository* with **Keep this code
private** ticked.

## 3. Create the Web App

Azure portal → **Create a resource → Web App**.

| | |
|---|---|
| Name | `titanintranet` |
| Publish | Code |
| Runtime | **Python 3.12** |
| OS | Linux |
| Region | the same as titantickets |
| Pricing plan | **the existing plan** — pick it from the list, do not create one |

Picking the existing App Service Plan is what makes this free. A new plan would
double the bill for no benefit.

## 4. Startup command and settings

**Configuration → General settings → Startup Command:**

```
gunicorn --bind=0.0.0.0:$PORT --workers=2 --timeout=120 app:app
```

No `--chdir` here. `app.py` is at the root of this repository, unlike the ticket
one where it lives under `webapp/`.

**Environment variables** — copy these across from `titantickets`:

```
DATABASE_URL          SECRET_KEY            OFFICE_PASSCODE
TENANT_ID             AUTH_CLIENT_ID        GRAPH_CLIENT_ID
GRAPH_CLIENT_SECRET   PORTAL_ADMINS         ORIENTATION_USERS
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

There is no `AUTH_CLIENT_SECRET` anywhere — `titan_auth` falls back to
`GRAPH_CLIENT_SECRET`, so one secret covers both sign-in and SharePoint.

Do **not** copy `MAIL_*`, `OCR_*` or `RUN_WORKER`. There is no worker in this
codebase, so there is nothing for them to turn on or off.

`PORTAL_ADMINS` matters: it is what gets you into `/access` before any groups
exist. Without it the Access screen locks everybody out, including you.

## 5. Give GitHub the publish profile

Azure → titanintranet → **Download publish profile** (top bar). Open the file,
copy all of it.

GitHub → the `titan-intranet` repo → **Settings → Secrets and variables →
Actions → New repository secret**:

- Name: `AZUREAPPSERVICE_PUBLISHPROFILE_TITANINTRANET`
- Value: the whole file

## 6. Register the temporary callback

So the site can be signed into and tested **before** the domain moves.

Entra → App registrations → the app in `AUTH_CLIENT_ID` → **Authentication →
Add a redirect URI**:

```
https://titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net/auth/callback
```

> **Use the full hostname Azure gave the app**, not `titanintranet.azurewebsites.net`.
> Azure now issues regional names with a hash in them. The short form does not
> exist and a redirect URI that does not match character for character fails at
> sign-in with a message about the reply URL. Azure → titanintranet →
> **Overview → Default domain** is the authority.

`https://intranet.tetransports.com/auth/callback` is already registered from
before and does not change — the hostname is the same, only the app behind it
moves.

Keeping the `azurewebsites.net` callback alongside is what the ticket site's own
DEPLOY.md recommends while sites move. Remove it afterwards if you like.

## 7. Deploy and test it on its Azure address

The push in step 2 may already have run the workflow. If not, GitHub →
**Actions → Build and deploy - titanintranet → Run workflow**.

Then check, in this order:

1. `https://titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net/healthz` — no sign-in needed. It
   should say `"ok": true` with `config: ok` and `database: ok`. If the database
   is not ok, `DATABASE_URL` did not come across.
2. `https://titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net/` — sign in. The intranet should
   appear exactly as it does today.
3. `https://titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net/access` — the Access screen, with
   six groups on it.

**Everything must work here before step 8.** After the domain moves there is no
second address to fall back to.

## 8. Move the domain

This is the only step with a gap in service, a minute or two while the
certificate is issued. Do it when nobody is on the intranet.

1. **titantickets → Custom domains → `intranet.tetransports.com` → Delete.**
   It has to leave the old app before it can join the new one.
2. **DNS** — repoint the `intranet` CNAME to
   `titanintranet-b7bghzcdcxewgjd7.canadacentral-01.azurewebsites.net`
   — the full hostname again, not the short form — and update the
   `asuid.intranet` TXT record to the value the next step shows you. (This is
   also the slow part: the old record may be cached for as long as its TTL.)
3. **titanintranet → Custom domains → Add custom domain →**
   `intranet.tetransports.com` → validate → add.
4. **Create App Service Managed Certificate** for it, then **bind** it, SNI SSL.
5. Open `https://intranet.tetransports.com` and sign in.

## 9. Clean up the ticket repository

Only now, once the new site is answering on the real address.

Run **`Finish the split.cmd`** in this folder. It lists what it will delete,
asks for `YES`, then removes the old copy from the ticket repository and the
duplicates here.

Then in `Desktop\Ticket Import Review`:

```
git add -A
git commit -m "Intranet moved to its own repository"
git push
```

That push deploys the ticket site once, with the intranet removed and a redirect
left in its place, so old `/intranet` bookmarks land on the new address.

---

## Afterwards

**Changing what is on the intranet** — edit `site/config.json`, commit, push.
Only the intranet deploys.

**Changing who sees what** — the Access screen. No deploy at all.

**Changing the ticket site** — the intranet does not notice.

## If something is wrong

`/healthz` first. It answers without a sign-in and says which of config,
database and auth is unhappy.

| Symptom | Usually |
|---------|---------|
| Sign-in loops, or "reply URL" error | the callback in step 6 is missing |
| "The intranet has no configuration" | `site/config.json` did not deploy |
| Access screen says it is for administrators | `PORTAL_ADMINS` is not set on this app |
| Cards missing that should be there | rules left over in the database — the Access screen shows them |
| Packet popup says not configured | `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` did not come across |

The database is shared with the ticket site, so every group and rule you made
before the split is still there.
