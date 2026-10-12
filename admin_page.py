"""admin-site-v1: the one page behind intranet.tetransports.com/admin.

One file, no build, no outside scripts - it has to open on a phone over a weak
signal when something is already wrong. Sections down the left on a computer,
tabs along the bottom on a phone. Everything it shows comes from /admin/api/*
and every change it makes goes back there with the page's own header.
"""

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1A2470">
<title>Titan admin</title>
<link rel="icon" href="/images/favicon.png">
<style>
:root{--navy:#243090;--navy-d:#1A2470;--accent:#00AAE6;--ink:#1C2230;--soft:#5a6475;--line:#dde3ee;
  --page:#eef2f7;--card:#fff;--good:#1a7f4b;--good-bg:#e7f6ee;--bad:#C4121D;--bad-bg:#fde8e8;--warn:#a15c00;
  --warn-bg:#fff4dc;--tint:#e8eaf8;--r:14px}
*{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:20;background:var(--navy-d);color:#fff;display:flex;align-items:center;gap:12px;
  padding:10px 16px;padding-top:calc(10px + env(safe-area-inset-top))}
header .plate{background:#fff;border-radius:9px;width:34px;height:34px;display:grid;place-items:center;flex:none}
header .plate img{height:24px}
header b{font-size:16px;display:block}
header small{color:#c7cdf0;font-size:12px}
header .sp{flex:1}
header button{background:rgba(255,255,255,.14);color:#fff;border:1px solid rgba(255,255,255,.3);border-radius:9px;
  height:34px;min-width:38px;font:inherit;font-size:13px;cursor:pointer;padding:0 10px}
.wrap{display:flex;min-height:calc(100vh - 54px)}
nav.side{width:210px;flex:none;padding:14px 10px;border-right:1px solid var(--line);background:#f8fafc}
nav.side a,nav.tabs a{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;color:var(--ink);
  text-decoration:none;font-weight:600;font-size:14px;cursor:pointer}
nav.side a:hover{background:var(--tint)}
nav.side a.on{background:var(--navy);color:#fff}
nav .ic{width:20px;text-align:center;font-size:16px}
main{flex:1;min-width:0;padding:18px 20px 90px;max-width:1150px}
h1{font-size:21px;margin:2px 0 4px}
.lead{color:var(--soft);margin:0 0 16px;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:14px 16px;box-shadow:0 2px 8px rgba(20,30,60,.05);margin-bottom:12px}
.card h2{font-size:15px;margin:0 0 8px;display:flex;align-items:center;gap:8px}
.card h2 .sp{flex:1}
.kv{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid #f0f2f6;font-size:14px}
.kv:last-child{border-bottom:0}
.kv span:first-child{color:var(--soft)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:#aab;flex:none}
.dot.ok{background:#22a35a}.dot.bad{background:var(--bad)}.dot.warn{background:#e8a317}
.pill{display:inline-block;font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:999px;background:var(--tint);color:var(--navy);white-space:nowrap}
.pill.ok{background:var(--good-bg);color:var(--good)}.pill.bad{background:var(--bad-bg);color:var(--bad)}.pill.warn{background:var(--warn-bg);color:var(--warn)}
.btn{font:inherit;font-size:13.5px;font-weight:600;padding:8px 13px;border-radius:10px;border:1px solid var(--line);background:#fff;
  color:var(--ink);cursor:pointer;white-space:nowrap}
.btn:hover{background:var(--tint)}
.btn.pri{background:var(--navy);border-color:var(--navy);color:#fff}
.btn.danger{color:var(--bad);border-color:#f2c3c3}
.btn.sm{padding:4px 9px;font-size:12.5px}
.btn:disabled{opacity:.5;cursor:default}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
input,select,textarea{font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);max-width:100%}
textarea{width:100%;min-height:60px}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--tint)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--soft);padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:7px 8px;border-bottom:1px solid #f0f2f6;vertical-align:top}
.tw{overflow-x:auto}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;word-break:break-all}
.muted{color:var(--soft);font-size:13px}
.err{background:var(--bad-bg);color:var(--bad);border-radius:10px;padding:9px 12px;font-size:13.5px;margin:6px 0}
.note{background:var(--warn-bg);color:#6b4500;border-radius:10px;padding:9px 12px;font-size:13.5px;margin:6px 0}
.people{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{display:inline-flex;align-items:center;gap:6px;background:var(--page);border:1px solid var(--line);border-radius:999px;padding:3px 4px 3px 10px;font-size:13px}
.chip button{border:0;background:none;color:var(--bad);font-size:15px;cursor:pointer;padding:0 6px}
details{margin-top:6px}
summary{cursor:pointer;font-weight:600;font-size:13.5px;color:var(--navy)}
.set{display:grid;grid-template-columns:minmax(150px,240px) 1fr auto;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid #f0f2f6}
.set .nm{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;word-break:break-all}
.set .help{grid-column:1/-1;color:var(--soft);font-size:12.5px;margin-top:-4px}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:84px;z-index:50;background:var(--ink);color:#fff;padding:10px 16px;border-radius:12px;
  font-size:14px;display:none;max-width:92vw;box-shadow:0 8px 30px rgba(0,0,0,.3)}
#toast.bad{background:var(--bad)}
nav.tabs{display:none}
.spin{display:inline-block;width:16px;height:16px;border:2px solid var(--line);border-top-color:var(--navy);border-radius:50%;animation:sp .8s linear infinite;vertical-align:-3px}
@keyframes sp{to{transform:rotate(360deg)}}
@media (max-width:760px){
  nav.side{display:none}
  main{padding:14px 12px 96px}
  nav.tabs{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:30;background:#fff;border-top:1px solid var(--line);
    overflow-x:auto;padding:6px 6px calc(6px + env(safe-area-inset-bottom));gap:2px;scrollbar-width:none}
  nav.tabs a{flex-direction:column;gap:2px;font-size:11px;padding:6px 10px;min-width:68px;justify-content:center;text-align:center}
  nav.tabs a.on{background:var(--tint);color:var(--navy)}
  .set{grid-template-columns:1fr;gap:4px}
  header small{display:none}
  .grid{grid-template-columns:1fr}
  td,th{padding:6px 5px}
}
</style></head>
<body>
<header>
  <span class="plate"><img src="/images/titan-energy-helmet.png" alt=""></span>
  <div><b>Titan admin</b><small id="who"></small></div>
  <span class="sp"></span>
  <button onclick="load()" title="Refresh this section" aria-label="Refresh">&#x21bb;</button>
  <button onclick="location.href='/'" title="Back to the intranet">Intranet</button>
</header>
<div class="wrap">
  <nav class="side" id="side"></nav>
  <main id="main"><span class="spin"></span></main>
</div>
<nav class="tabs" id="tabs"></nav>
<div id="toast"></div>
<script>
const ME = __ME__;
const SECTIONS = [['overview','&#9673;','Overview'],['access','&#128273;','Access'],['settings','&#9881;','Settings'],
  ['work','&#9993;','Mail & OCR'],['restore','&#8634;','Restore'],['database','&#128452;','Database'],['activity','&#9776;','Activity']];
let cur = (location.hash || '#overview').slice(1);
if(!SECTIONS.some(s => s[0] === cur)) cur = 'overview';
document.getElementById('who').textContent = ME.name || ME.email;

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function ago(t){
  if(!t) return 'never';
  const s = (Date.now() - new Date(t).getTime()) / 1000;
  if(isNaN(s)) return esc(t);
  if(s < 0) return s > -5400 ? 'in ' + Math.round(-s / 60) + ' min' : 'in ' + Math.round(-s / 3600) + ' h';
  if(s < 90) return Math.round(s) + 's ago';
  if(s < 5400) return Math.round(s / 60) + ' min ago';
  if(s < 172800) return Math.round(s / 3600) + ' h ago';
  return Math.round(s / 86400) + ' days ago';
}
function when(t){ if(!t) return ''; const d = new Date(t); return isNaN(d) ? esc(t) : d.toLocaleString([], {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}); }
function toast(msg, bad){ const t = document.getElementById('toast'); t.textContent = msg; t.className = bad ? 'bad' : '';
  t.style.display = 'block'; clearTimeout(t._t); t._t = setTimeout(() => t.style.display = 'none', bad ? 6000 : 3000); }
async function api(path, body){
  const r = await fetch('/admin/api/' + path, body === undefined ? {headers: {'X-Requested-With': 'fetch'}}
    : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Requested-With': 'fetch'}, body: JSON.stringify(body)});
  let j = null; try{ j = await r.json(); }catch(e){}
  if(r.status === 401){ location.href = '/login?next=/admin'; throw new Error('signed out'); }
  if(!r.ok || !j || j.ok === false && !j.missing) throw new Error((j && j.error) || ('HTTP ' + r.status));
  return j;
}
async function act(path, body, said, again){
  try{ const j = await api(path, body); toast(said || 'Done'); if(again !== false) load(); return j; }
  catch(e){ toast(e.message, true); }
}
function errBox(x){ return x && x.error ? '<div class="err">' + esc(x.error) + '</div>' : ''; }
function nav(){
  const h = SECTIONS.map(([k, ic, l]) => '<a class="' + (k === cur ? 'on' : '') + '" onclick="go(\'' + k + '\')"><span class="ic">' + ic + '</span>' + l + '</a>').join('');
  document.getElementById('side').innerHTML = h; document.getElementById('tabs').innerHTML = h;
}
function go(k){ cur = k; history.replaceState(null, '', '#' + k); nav(); load(); window.scrollTo(0, 0); }
async function load(){
  const m = document.getElementById('main');
  m.innerHTML = '<span class="spin"></span>';
  try{ await R[cur](m); }catch(e){ m.innerHTML = '<div class="err">' + esc(e.message) + '</div>'; }
}
const R = {};

/* ---- overview ---------------------------------------------------------- */
R.overview = async m => {
  const j = await api('overview');
  let h = '<h1>Overview</h1><p class="lead">Every site and what it is doing. Checked ' + when(j.at) + '.</p>';
  h += '<div class="card"><h2>Sites</h2>' + j.sites.map(s => '<div class="kv"><span><span class="dot ' + (s.ok ? 'ok' : 'bad') + '"></span> '
    + esc(s.name) + '</span><span>' + (s.ok ? '<span class="pill ok">up</span>' : '<span class="pill bad">' + (s.status || 'down') + '</span>')
    + ' <span class="muted">' + (s.ms ? s.ms + ' ms' : '') + '</span></span></div>'
    + (s.detail && (s.detail.mail || s.detail.error || s.detail.missing) ? '<div class="muted" style="margin:-2px 0 6px 18px">'
      + esc(s.detail.error || ('mail: ' + (s.detail.mail || '')) + (s.detail.missing ? ' · missing ' + s.detail.missing : '')) + '</div>' : '')).join('') + '</div>';
  h += '<div class="grid">';
  const t = j.tickets || {};
  h += '<div class="card"><h2>Tickets</h2>' + errBox(t);
  if(!t.error){
    const st = Object.fromEntries((t.jobs || []).map(r => [r.state, r.n]));
    h += kv('Tray', (t.tray && t.tray.n || 0) + ' scans' + (t.tray && t.tray.oldest ? ' · oldest ' + ago(t.tray.oldest) : ''))
      + kv('OCR queue', (st.queued || 0) + ' waiting, ' + (st.running || 0) + ' running')
      + kv('Last 24 h', (st.done || 0) + ' done · ' + (st.failed ? '<span class="pill bad">' + st.failed + ' failed</span>' : '0 failed'))
      + kv('Mail', t.mail ? ((t.mail.ok ? '<span class="pill ok">ok</span> ' : '<span class="pill bad">failing</span> ') + ago(t.mail.checked_at)) : 'no check yet')
      + kv('Last batch', t.last_batch ? esc(t.last_batch.batch_id) + ' · ' + ago(t.last_batch.added_at) : '-');
    if(t.last_failed) h += '<div class="muted">Last failure #' + t.last_failed.id + ': ' + esc(t.last_failed.error || '') + '</div>';
  }
  h += '<div class="row" style="margin-top:8px"><button class="btn sm" onclick="act(\'work/run-now\', {}, \'Asked the ticket worker to check mail and run now\')">Check mail + run now</button></div></div>';
  const a = j.ap || {};
  h += '<div class="card"><h2>Accounts payable</h2>' + errBox(a);
  if(!a.error){
    h += kv('To review', (a.waiting || {}).to_review || 0) + kv('Ready for QuickBooks', (a.waiting || {}).ready_for_qb || 0) + kv('Sorting tray', (a.waiting || {}).tray || 0);
    (a.mailboxes || []).forEach(b => { const l = b.last || {};
      h += kv(esc(b.mailbox), l.at ? ((l.ok ? '<span class="pill ok">ok</span> ' : '<span class="pill bad">not working</span> ') + ago(l.at)) : 'never checked');
      if(l.ok === false && l.error) h += '<div class="muted">' + esc(l.error) + '</div>'; });
  }
  h += '</div>';
  const d = j.dispatch || {};
  h += '<div class="card"><h2>Dispatch</h2>' + errBox(d);
  if(!d.error){
    const age = d.tanks && d.tanks.age_s;
    h += kv('Tank readings', d.tanks && d.tanks.last_stored ? '<span class="pill ' + (age > 7200 ? 'warn' : 'ok') + '">' + ago(d.tanks.last_stored) + '</span>' : 'none')
      + kv('Last board send', d.board_push ? esc(d.board_push.batch_id) + ' · ' + ago(d.board_push.pushed_at) : 'none');
  }
  h += '</div>';
  const db = j.database || {};
  h += '<div class="card"><h2>Database</h2>' + errBox(db) + (db.error ? '' : kv('Size', esc(db.size)) + kv('Connections', db.connections)
    + kv('Stuck', db.stuck ? '<span class="pill warn">' + db.stuck + ' stuck</span> <a onclick="go(\'database\')" style="color:var(--navy);cursor:pointer">see</a>' : 'none')) + '</div>';
  h += '</div>';
  m.innerHTML = h;
};
function kv(k, v){ return '<div class="kv"><span>' + k + '</span><span>' + v + '</span></div>'; }

/* ---- access ------------------------------------------------------------ */
R.access = async m => {
  const j = await api('access');
  let h = '<h1>Access</h1><p class="lead">Who may open which site. Every Titan site checks this list when someone signs in.</p>';
  h += errBox(j.sites);
  (Array.isArray(j.sites) ? j.sites : []).forEach(s => {
    h += '<div class="card"><h2>' + esc(s.name || s.slug) + ' <span class="pill">' + esc(s.slug) + '</span>'
      + (s.open_to_all ? ' <span class="pill warn">everyone at Titan</span>' : '') + (s.live === false ? ' <span class="pill bad">off</span>' : '')
      + '<span class="sp"></span><span class="muted">' + (s.people || []).length + '</span></h2>'
      + '<div class="muted mono">' + esc(s.url || '') + '</div>'
      + '<div class="people">' + (s.people || []).map(p => '<span class="chip" title="Given by ' + esc(p.granted_by || '?') + ' ' + when(p.granted_at) + '">'
        + esc(p.email) + '<button onclick="revoke(\'' + esc(s.slug) + '\',\'' + esc(p.email) + '\')" aria-label="Remove">&times;</button></span>').join('')
      + ((s.people || []).length ? '' : '<span class="muted">' + (s.open_to_all ? 'Open to everyone - no list needed.' : 'Nobody yet.') + '</span>') + '</div>'
      + '<div class="row"><input id="g_' + esc(s.slug) + '" placeholder="email@tetransports.com (or several)" style="flex:1;min-width:200px">'
      + '<button class="btn pri" onclick="grant(\'' + esc(s.slug) + '\')">Give access</button></div>'
      + '<details><summary>Site settings</summary><div class="row" style="margin-top:8px">'
      + '<input id="n_' + esc(s.slug) + '" value="' + esc(s.name || '') + '" placeholder="Name">'
      + '<input id="u_' + esc(s.slug) + '" value="' + esc(s.url || '') + '" placeholder="https://..." style="flex:1">'
      + '<button class="btn" onclick="siteSave(\'' + esc(s.slug) + '\')">Save</button></div><div class="row" style="margin-top:8px">'
      + '<button class="btn" onclick="siteFlag(\'' + esc(s.slug) + '\',\'live\',' + (s.live === false) + ')">' + (s.live === false ? 'Turn on' : 'Turn off (hide tile)') + '</button>'
      + '<button class="btn ' + (s.open_to_all ? '' : 'danger') + '" onclick="siteFlag(\'' + esc(s.slug) + '\',\'open_to_all\',' + !s.open_to_all + ')">'
      + (s.open_to_all ? 'Limit to the list' : 'Open to everyone at Titan') + '</button></div></details></div>';
  });
  h += '<div class="card"><h2>Add a site</h2><div class="row"><input id="ns_slug" placeholder="short name, e.g. titan-bids">'
    + '<input id="ns_name" placeholder="Name"><input id="ns_url" placeholder="https://..." style="flex:1"><button class="btn pri" onclick="addSite()">Add</button></div>'
    + '<p class="muted">The short name is what the app is configured with (SITE_SLUG) and cannot be changed later.</p></div>';
  h += '<div class="card"><h2>Admins</h2>' + kv('This admin page', esc((j.admin_site_users || []).join(', ')) + ' <span class="muted">(ADMIN_SITE_USERS)</span>')
    + kv('Break-glass, every site', esc((j.breakglass || []).join(', ') || 'none') + ' <span class="muted">(PORTAL_ADMINS)</span>');
  const pa = Array.isArray(j.portal_admins) ? j.portal_admins : [];
  h += '<div class="muted" style="margin-top:8px">Portal admins</div><div class="people">' + pa.map(p => '<span class="chip">' + esc(p.email)
    + '<button onclick="act(\'access/portal-admin\', {email:\'' + esc(p.email) + '\', remove:true}, \'Removed\')">&times;</button></span>').join('') + '</div>'
    + '<div class="row"><input id="pa_new" placeholder="email"><button class="btn" onclick="act(\'access/portal-admin\', {email: document.getElementById(\'pa_new\').value}, \'Added\')">Add portal admin</button></div></div>';
  const it = j.intranet || {};
  h += '<div class="card"><h2>Intranet groups</h2>' + errBox(it);
  if(!it.error){
    const gs = it.groups || [];
    h += '<div class="tw"><table><tr><th>Person</th>' + gs.map(g => '<th>' + esc(g.label || g.name) + '</th>').join('') + '</tr>'
      + (it.members || []).map(p => '<tr><td class="mono">' + esc(p.email) + '</td>' + gs.map(g => '<td><input type="checkbox" '
        + (p.groups.includes(g.name) ? 'checked ' : '') + 'onchange="setGroups(this,\'' + esc(p.email) + '\')" data-g="' + esc(g.name) + '"></td>').join('') + '</tr>').join('')
      + '</table></div><div class="row" style="margin-top:8px"><input id="ig_new" placeholder="email"><select id="ig_g">'
      + gs.map(g => '<option value="' + esc(g.name) + '">' + esc(g.label || g.name) + '</option>').join('') + '</select>'
      + '<button class="btn" onclick="act(\'access/intranet\', {email: document.getElementById(\'ig_new\').value, groups:[document.getElementById(\'ig_g\').value]}, \'Added\')">Add to group</button></div>';
  }
  h += '</div>';
  m.innerHTML = h;
};
function grant(slug){ const v = document.getElementById('g_' + slug).value; if(!v.trim()) return; act('access/grant', {slug, emails: v}, 'Access given'); }
function revoke(slug, email){ if(confirm('Take ' + email + ' off ' + slug + '?')) act('access/revoke', {slug, email}, 'Removed'); }
function siteSave(slug){ act('access/site', {slug, name: document.getElementById('n_' + slug).value, url: document.getElementById('u_' + slug).value}, 'Saved'); }
function siteFlag(slug, k, v){
  const b = {slug}; b[k] = v;
  if(k === 'open_to_all' && v){ const c = prompt('This lets EVERYONE at Titan into ' + slug + '. Type ' + slug + ' to confirm.'); if(!c) return; b.confirm = c; }
  act('access/site', b, 'Saved');
}
function addSite(){ act('access/site', {new: true, slug: document.getElementById('ns_slug').value, name: document.getElementById('ns_name').value, url: document.getElementById('ns_url').value}, 'Site added'); }
function setGroups(box, email){
  const groups = [...box.closest('tr').querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.dataset.g);
  act('access/intranet', {email, groups}, 'Saved', false);
}

/* ---- settings (Azure) -------------------------------------------------- */
let AZ = null, AZAPP = null;
R.settings = async m => {
  const j = AZ || await api('azure/apps');
  let h = '<h1>Settings</h1><p class="lead">Each web app\'s settings in Azure. Changing one restarts that app (about 30 seconds). Secrets can be replaced but never shown.</p>';
  if(j.missing){
    h += '<div class="card"><h2>Not connected to Azure yet</h2><p>This needs one Azure login for the admin page. Missing on the intranet app: <b>' + esc(j.missing.join(', '))
      + '</b>.</p><p class="muted">The steps are in <b>Admin site - walkthrough.md</b> in the Intranet folder. Until then, the switches below are listed for reference.</p></div>';
    h += switchList(j.switches || [], null, {});
    m.innerHTML = h; return;
  }
  AZ = j;
  const apps = j.apps || [];
  if(!AZAPP || !apps.some(a => a.name === AZAPP)) AZAPP = (apps.find(a => /tickets$/.test(a.name)) || apps[0] || {}).name;
  h += '<div class="card"><div class="row"><label class="muted">App</label><select id="azapp" onchange="AZAPP=this.value;load()" style="flex:1">'
    + apps.map(a => '<option value="' + esc(a.name) + '"' + (a.name === AZAPP ? ' selected' : '') + '>' + esc(a.name) + (a.state && a.state !== 'Running' ? ' (' + esc(a.state) + ')' : '') + '</option>').join('')
    + '</select><button class="btn danger" onclick="restartApp()">Restart</button></div>';
  const app = apps.find(a => a.name === AZAPP) || {};
  h += '<div class="muted" style="margin-top:6px">' + esc((app.hosts || []).join(' · ')) + '</div></div>';
  m.innerHTML = h + '<span class="spin"></span>';
  const s = await api('azure/settings?app=' + encodeURIComponent(AZAPP));
  const by = Object.fromEntries(s.settings.map(x => [x.name, x]));
  h += switchList(j.switches || [], AZAPP, by);
  h += '<div class="card"><h2>All settings on ' + esc(AZAPP) + '<span class="sp"></span><span class="muted">' + s.settings.length + '</span></h2>'
    + (s.test_target ? '<div class="note">This is a test app or slot: it is refused a database setting that matches production\'s.</div>' : '')
    + s.settings.map(x => setRow(x)).join('')
    + '<div class="row" style="margin-top:10px"><input id="new_n" placeholder="NEW_SETTING_NAME"><input id="new_v" placeholder="value" style="flex:1">'
    + '<button class="btn pri" onclick="setVal(document.getElementById(\'new_n\').value, document.getElementById(\'new_v\').value)">Add</button></div></div>';
  m.innerHTML = h;
};
function setRow(x){
  const id = 'v_' + x.name;
  return '<div class="set"><span class="nm">' + esc(x.name) + (x.guarded ? ' <span class="pill warn">guarded</span>' : '') + '</span>'
    + (x.secret ? '<input id="' + esc(id) + '" type="password" placeholder="' + esc(x.hint) + ' - type a new value to replace" autocomplete="new-password">'
              : '<input id="' + esc(id) + '" value="' + esc(x.value) + '">')
    + '<span class="row"><button class="btn sm" onclick="setVal(\'' + esc(x.name) + '\', document.getElementById(\'' + esc(id) + '\').value, ' + x.guarded + ', ' + x.secret + ')">Save</button>'
    + '<button class="btn sm danger" onclick="delVal(\'' + esc(x.name) + '\', ' + x.guarded + ')" title="Delete this setting">&times;</button></span></div>';
}
function switchList(sw, app, by){
  let h = '<div class="card"><h2>Switches</h2><p class="muted" style="margin-top:0">The settings the sites run on, with what each does.' + (app ? ' Shown for ' + esc(app) + '.' : '') + '</p>';
  sw.forEach(s => {
    const have = by[s.name], v = have ? (have.secret ? '' : have.value) : '';
    let ctl;
    if(!app) ctl = '<span class="pill">' + esc(s.site) + '</span>';
    else if(s.kind === 'choice') ctl = '<select id="sw_' + s.name + '"><option value="">(not set)</option>' + s.choices.map(c => '<option' + (c === v ? ' selected' : '') + '>' + c + '</option>').join('') + '</select>';
    else if(s.kind === 'bool') ctl = '<select id="sw_' + s.name + '"><option value="">(not set)</option><option value="1"' + (/^(1|true|on|yes)$/i.test(v) ? ' selected' : '') + '>on</option><option value="0"' + (/^(0|false|off|no)$/i.test(v) ? ' selected' : '') + '>off</option></select>';
    else ctl = '<input id="sw_' + s.name + '" value="' + esc(v) + '"' + (s.kind === 'number' ? ' inputmode="numeric"' : '') + '>';
    h += '<div class="set"><span class="nm">' + esc(s.name) + ' <span class="pill">' + esc(s.site) + '</span>' + (app && !have ? ' <span class="muted">not set</span>' : '') + '</span>' + ctl
      + (app ? '<button class="btn sm" onclick="setVal(\'' + s.name + '\', document.getElementById(\'sw_' + s.name + '\').value, ' + (s.name === 'PORTAL_ADMINS') + ')">Save</button>' : '<span></span>')
      + '<div class="help">' + esc(s.help) + '</div></div>';
  });
  return h + '</div>';
}
async function setVal(name, value, guarded, secret){
  name = (name || '').trim(); if(!name) return;
  if(secret && !value){ toast('Type the new value first', true); return; }
  let confirmName = '';
  if(guarded){ confirmName = prompt(name + ' is guarded. Type the app name (' + AZAPP.split('/')[0] + ') to change it.'); if(!confirmName) return; }
  else if(!confirm('Set ' + name + ' on ' + AZAPP + '? The app restarts.')) return;
  await act('azure/set', {app: AZAPP, name, value, confirm: confirmName}, name + ' saved - ' + AZAPP + ' is restarting');
}
async function delVal(name, guarded){
  let c = '';
  if(guarded){ c = prompt('Delete guarded setting ' + name + '? Type the app name to confirm.'); if(!c) return; }
  else if(!confirm('Delete ' + name + ' from ' + AZAPP + '? The app restarts.')) return;
  await act('azure/set', {app: AZAPP, name, delete: true, confirm: c}, name + ' deleted');
}
async function restartApp(){
  const c = prompt('Restart ' + AZAPP + '? It is down for about 30 seconds. Type ' + AZAPP.split('/')[0] + ' to confirm.');
  if(c) await act('azure/restart', {app: AZAPP, confirm: c}, AZAPP + ' is restarting', false);
}

/* ---- mail & OCR -------------------------------------------------------- */
R.work = async m => {
  const j = await api('work');
  let h = '<h1>Mail &amp; OCR</h1><p class="lead">The ticket worker, the scan queue and the AP mailboxes.</p>';
  h += '<div class="card"><h2>Ticket worker<span class="sp"></span><button class="btn sm pri" onclick="act(\'work/run-now\', {}, \'Asked - the worker picks it up within a minute\')">Check mail + run now</button></h2>';
  if(j.mail && !j.mail.error) h += kv('Mail check', (j.mail.ok ? '<span class="pill ok">ok</span> ' : '<span class="pill bad">failing</span> ') + ago(j.mail.checked_at) + (j.mail.waiting != null ? ' · ' + j.mail.waiting + ' waiting' : ''));
  h += errBox(j.mail);
  (Array.isArray(j.requests) ? j.requests : []).forEach(r => h += kv('Asked: ' + esc(r.kind), esc(r.asked_by || '') + ' ' + ago(r.asked_at) + (r.taken_at ? ' · taken ' + ago(r.taken_at) : ' · <span class="pill warn">not taken yet</span>')));
  h += '</div>';
  h += '<div class="card"><h2>OCR jobs</h2>' + errBox(j.jobs) + '<div class="tw"><table><tr><th>#</th><th>State</th><th>What</th><th>When</th><th></th></tr>'
    + (Array.isArray(j.jobs) ? j.jobs : []).map(x => '<tr><td>' + x.id + '</td><td><span class="pill ' + ({failed:'bad', done:'ok', running:'warn'}[x.state] || '') + '">' + esc(x.state) + '</span></td><td>'
      + esc(x.batch_id || x.subject || x.kind) + (x.pages_total ? ' <span class="muted">' + x.pages_done + '/' + x.pages_total + ' pages</span>' : '')
      + (x.error ? '<div class="muted">' + esc(x.error) + '</div>' : '') + '</td><td class="muted">' + when(x.finished_at || x.started_at || x.queued_at)
      + (x.state === 'queued' && x.run_after ? '<br>runs ' + when(x.run_after) : '') + '</td><td>'
      + (x.state === 'failed' || x.state === 'cancelled' ? '<button class="btn sm" onclick="act(\'work/job\', {id:' + x.id + ', action:\'retry\'}, \'Queued again\')">Retry</button>' : '')
      + (x.state === 'queued' ? '<button class="btn sm" onclick="act(\'work/job\', {id:' + x.id + ', action:\'now\'}, \'Runs on the next tick\')">Run now</button> <button class="btn sm danger" onclick="if(confirm(\'Cancel job ' + x.id + '?\')) act(\'work/job\', {id:' + x.id + ', action:\'cancel\'}, \'Cancelled\')">Cancel</button>' : '')
      + '</td></tr>').join('') + '</table></div></div>';
  h += '<div class="card"><h2>Scans in the tray<span class="sp"></span><span class="muted">' + (Array.isArray(j.tray) ? j.tray.length : '') + '</span></h2>' + errBox(j.tray)
    + (Array.isArray(j.tray) ? j.tray.map(p => kv(esc(p.filename || ('#' + p.id)), p.tickets + ' tickets · ' + ago(p.created_at))).join('') : '')
    + '<details><summary>Discarded scans (put one back)</summary>' + (Array.isArray(j.discarded) ? j.discarded.map(p => '<div class="kv"><span>' + esc(p.filename || ('#' + p.id))
      + ' <span class="muted">' + esc(p.resolved_by || '') + ' ' + ago(p.resolved_at) + '</span></span><button class="btn sm" onclick="act(\'work/packet-restore\', {id:' + p.id + '}, \'Back in the tray\')">Back to tray</button></div>').join('') : errBox(j.discarded)) + '</details></div>';
  h += '<div class="card"><h2>AP mailboxes</h2>' + errBox(j.ap_mailboxes);
  (Array.isArray(j.ap_mailboxes) ? j.ap_mailboxes : []).forEach(b => { const l = b.last || {};
    h += '<div class="kv"><span>' + esc(b.mailbox) + '<br><span class="muted">reading from ' + when(b.reading_from) + '</span></span><span>'
      + (l.ok === false ? '<span class="pill bad">not working</span>' : l.at ? '<span class="pill ok">ok</span>' : '') + ' ' + ago(l.at) + '</span></div>'
      + (l.error ? '<div class="err">' + esc(l.error) + '</div>' : '')
      + '<div class="row" style="margin:4px 0 8px"><span class="muted">Look again from</span><select id="rr_' + esc(b.mailbox) + '"><option value="2">2 hours ago</option><option value="24">yesterday</option><option value="72">3 days ago</option><option value="168">a week ago</option></select>'
      + '<button class="btn sm" onclick="reread(\'' + esc(b.mailbox) + '\')">Re-read</button></div>'; });
  h += '<p class="muted">Re-reading never files an email twice: ones already taken are skipped. It picks up ones that failed or were forgotten below.</p>';
  h += '<details><summary>Emails that failed or were left out</summary>' + (Array.isArray(j.ap_problems) ? j.ap_problems.map(p => '<div class="kv"><span>' + esc(p.note) + '<br><span class="muted">' + ago(p.seen_at) + '</span></span>'
    + '<button class="btn sm" onclick="act(\'work/ap-forget\', {message_id: \'' + esc(p.message_id) + '\'}, \'Forgotten - it is read again on the next check from before it\')">Read again</button></div>').join('') || '<p class="muted">None.</p>' : errBox(j.ap_problems)) + '</details></div>';
  m.innerHTML = h;
};
function reread(box){ const hrs = document.getElementById('rr_' + box).value; act('work/ap-reread', {mailbox: box === '(main mailbox)' ? '' : box, hours: +hrs}, 'The next check looks back from then'); }

/* ---- restore ----------------------------------------------------------- */
R.restore = async m => {
  const j = await api('restore');
  let h = '<h1>Restore</h1><p class="lead">Put back what was cleared out. Nothing here deletes anything.</p>';
  h += '<div class="card"><h2>AP backups</h2>' + errBox(j.ap_backups);
  (Array.isArray(j.ap_backups) ? j.ap_backups : []).forEach(b => b.sets.forEach(s => {
    h += '<div class="kv"><span><b>' + (s.set === 'tray' ? 'Sorting tray items' : 'Invoices') + '</b> · ' + s.rows + ' items, ' + when(s.first) + ' – ' + when(s.last)
      + '<br><span class="muted mono">' + esc(b.schema) + '</span>' + (s.already_back ? ' <span class="pill">' + s.already_back + ' already back</span>' : '') + '</span>'
      + '<button class="btn sm" onclick="restoreSet(\'' + esc(b.schema) + '\',\'' + s.set + '\',' + s.rows + ')">Put back</button></div>'; }));
  if(Array.isArray(j.ap_backups) && !j.ap_backups.length) h += '<p class="muted">No backups.</p>';
  h += '</div><div class="card"><h2>Voided AP invoices</h2>' + errBox(j.ap_voided)
    + (Array.isArray(j.ap_voided) ? j.ap_voided.map(b => '<div class="kv"><span>' + esc(b.vendor || 'no vendor') + ' · ' + esc(b.bill_number || ('#' + b.id))
      + (b.total != null ? ' · $' + Number(b.total).toFixed(2) : '') + '<br><span class="muted">' + esc(b.note || '') + ' ' + ago(b.updated_at) + '</span></span>'
      + '<button class="btn sm" onclick="act(\'restore/ap-unvoid\', {id:' + b.id + '}, \'Reopened - it is back to review\')">Reopen</button></div>').join('') : '') + '</div>';
  m.innerHTML = h;
};
function restoreSet(schema, set, n){
  const c = prompt('Put back ' + n + ' ' + (set === 'tray' ? 'tray items' : 'invoices') + ' from ' + schema + '? Ones already there are skipped. Type restore to confirm.');
  if(c) act('restore/ap-backup', {schema, set, confirm: c}, 'Put back');
}

/* ---- database ---------------------------------------------------------- */
R.database = async m => {
  const j = await api('database');
  let h = '<h1>Database</h1><p class="lead">The shared Supabase database every site uses.</p>';
  h += '<div class="card"><h2>Connections</h2>' + errBox(j.connections) + '<div class="tw"><table><tr><th>Who</th><th>State</th><th>For</th><th>Doing</th><th></th></tr>'
    + (Array.isArray(j.connections) ? j.connections.map(c => '<tr><td>' + esc(c.app || c.who || '') + '</td><td><span class="pill ' + (c.state === 'idle in transaction' && c.for_s > 120 ? 'warn' : '') + '">' + esc(c.state || '') + '</span></td><td>'
      + (c.for_s != null ? Math.round(c.for_s / 60) + ' min' : '') + '</td><td class="mono">' + esc(c.query || '') + '</td><td>'
      + ((c.state === 'idle in transaction' && c.for_s > 60) || c.for_s > 300 ? '<button class="btn sm danger" onclick="if(confirm(\'End connection ' + c.pid + '? Its unfinished work is rolled back.\')) act(\'database/end\', {pid:' + c.pid + '}, \'Ended\')">End</button>' : '')
      + '</td></tr>').join('') : '') + '</table></div></div>';
  h += '<div class="grid"><div class="card"><h2>By schema</h2>' + errBox(j.schemas) + (Array.isArray(j.schemas) ? j.schemas.map(s => kv(esc(s.schema), esc(s.size))).join('') : '') + '</div>'
    + '<div class="card"><h2>Biggest tables</h2>' + errBox(j.tables) + (Array.isArray(j.tables) ? j.tables.map(t => kv('<span class="mono">' + esc(t.name) + '</span>', esc(t.size))).join('') : '') + '</div></div>';
  h += '<div class="card"><h2>Queries moving the most data</h2><p class="muted" style="margin-top:0">Where the database egress goes - since the counters were last reset.</p>' + errBox(j.heavy)
    + '<div class="tw"><table><tr><th>Rows</th><th>Calls</th><th>Per call</th><th>Query</th></tr>' + (Array.isArray(j.heavy) ? j.heavy.map(x => '<tr><td>' + Number(x.rows).toLocaleString() + '</td><td>'
      + Number(x.calls).toLocaleString() + '</td><td>' + Number(x.rows_per_call).toLocaleString() + '</td><td class="mono">' + esc(x.query) + '</td></tr>').join('') : '') + '</table></div></div>';
  m.innerHTML = h;
};

/* ---- activity ---------------------------------------------------------- */
R.activity = async m => {
  const j = await api('activity');
  let h = '<h1>Activity</h1><p class="lead">What changed recently, and everything done on this page.</p>';
  h += '<div class="card"><h2>This admin page</h2>' + errBox(j.admin_log) + (Array.isArray(j.admin_log) && j.admin_log.length ? j.admin_log.map(x => '<div class="kv"><span>' + esc(x.action) + ' <b>' + esc(x.target || '') + '</b><br><span class="muted">'
    + esc(x.who) + ' · ' + esc(x.area) + '</span></span><span class="muted">' + ago(x.at) + '</span></div>').join('') : '<p class="muted">Nothing yet.</p>') + '</div>';
  h += '<div class="card"><h2>Across the sites</h2>' + errBox(j.recent) + (Array.isArray(j.recent) ? j.recent.map(x => '<div class="kv"><span><span class="pill">' + esc(x.site) + '</span> ' + esc(x.what)
    + '<br><span class="muted">' + esc(x.who || '') + '</span></span><span class="muted">' + ago(x.at) + '</span></div>').join('') : '') + '</div>';
  m.innerHTML = h;
};

nav(); load();
</script>
</body></html>
"""
