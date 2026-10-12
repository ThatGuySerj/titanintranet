"""admin-site-v2: the one page behind intranet.tetransports.com/admin.

One file, no build, no outside scripts - it has to open on a phone over a weak
signal when something is already wrong. Sections down the left on a computer,
tabs along the bottom on a phone. Everything it shows comes from /admin/api/*
and every change it makes goes back there with the page's own header.

v2 (12 Oct 2026) is a re-skin of v1 for reading at a glance, with the same API
and the same confirmations:

  - Overview opens with one line: everything is fine, or the short list of
    what is not, each a link to where it is fixed.
  - Numbers are tiles with a word under them, not rows of key: value.
  - The technical parts - every Azure setting, database queries, table sizes,
    finished OCR jobs - are folded away under "Show ..." until wanted.
  - Values that go into a click handler are passed through q() (a JSON string,
    HTML-escaped), so an apostrophe in a name cannot break the button.
"""

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1A2470">
<title>Titan Admin</title>
<link rel="icon" href="/images/favicon.png">
<style>
:root{
  --navy:#243090;--navy-d:#1A2470;--navy-l:#eef0fb;--accent:#00AAE6;
  --ink:#172033;--soft:#5b6476;--faint:#8a92a3;--line:#e3e7ef;--line-2:#eef1f6;
  --page:#f4f6fa;--card:#fff;
  --good:#157347;--good-bg:#e6f5ec;--bad:#C4121D;--bad-bg:#fdecec;--warn:#9a5b00;--warn-bg:#fff4dc;
  --r:14px;--shadow:0 1px 2px rgba(20,30,60,.05),0 4px 14px rgba(20,30,60,.05)}
*{box-sizing:border-box}
html,body{margin:0;background:var(--page);color:var(--ink);
  font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit}
a{color:var(--navy)}

/* ---- top bar ---- */
header{position:sticky;top:0;z-index:20;background:var(--navy-d);color:#fff;display:flex;align-items:center;gap:12px;
  padding:10px 18px;padding-top:calc(10px + env(safe-area-inset-top));box-shadow:0 2px 10px rgba(10,15,50,.25)}
header .plate{background:#fff;border-radius:10px;width:36px;height:36px;display:grid;place-items:center;flex:none}
header .plate img{height:26px}
header .who b{font-size:16px;display:block;letter-spacing:.2px}
header .who small{color:#c3c9ee;font-size:12.5px}
header .sp{flex:1}
header .hb{background:rgba(255,255,255,.12);color:#fff;border:1px solid rgba(255,255,255,.25);border-radius:10px;
  height:36px;padding:0 12px;font-size:13.5px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
header .hb:hover{background:rgba(255,255,255,.22)}
header .hb svg{width:16px;height:16px}

/* ---- layout ---- */
.wrap{display:flex;min-height:calc(100vh - 56px)}
nav.side{width:224px;flex:none;padding:16px 12px;border-right:1px solid var(--line);background:#fff;
  position:sticky;top:56px;height:calc(100vh - 56px);overflow-y:auto}
nav a{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:10px;color:var(--ink);
  text-decoration:none;font-weight:600;font-size:14.5px;cursor:pointer;margin-bottom:2px}
nav.side a:hover{background:var(--navy-l)}
nav.side a.on{background:var(--navy);color:#fff}
nav a svg{width:19px;height:19px;flex:none;opacity:.85}
nav a .flag{margin-left:auto;width:8px;height:8px;border-radius:50%;background:var(--bad)}
main{flex:1;min-width:0;padding:24px 28px 100px;max-width:1120px}
.ph{margin:0 0 18px}
.ph h1{font-size:24px;line-height:1.2;margin:0 0 4px;letter-spacing:-.2px}
.ph p{color:var(--soft);margin:0;font-size:14.5px}

/* ---- cards ---- */
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--shadow);margin-bottom:16px}
.ch{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line-2)}
.ch h2{font-size:16px;margin:0;flex:1;min-width:0}
.ch .sub{font-weight:400;color:var(--soft);font-size:13px;margin-left:6px}
.cb{padding:14px 18px}
.cb.flush{padding:0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;align-items:start}
.cols .card{margin-bottom:0}
.stack{display:flex;flex-direction:column;gap:16px;margin-bottom:16px}

/* ---- the one-line status ---- */
.banner{display:flex;gap:14px;align-items:flex-start;border-radius:var(--r);padding:16px 18px;margin-bottom:18px;border:1px solid}
.banner.ok{background:var(--good-bg);border-color:#bfe5cf;color:#0f5132}
.banner.bad{background:var(--bad-bg);border-color:#f5c2c2;color:#7a0b12}
.banner .big{font-size:17px;font-weight:700;margin:0}
.banner ul{margin:6px 0 0;padding-left:18px}
.banner li{margin:2px 0}
.banner a{color:inherit;font-weight:600}
.banner svg{width:26px;height:26px;flex:none;margin-top:1px}

/* ---- numbers ---- */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.stat{background:var(--page);border-radius:12px;padding:12px 14px}
.stat .n{font-size:26px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums}
.stat .l{font-size:13px;color:var(--soft);margin-top:2px}
.stat .s{font-size:12px;color:var(--faint);margin-top:2px}
.stat.bad{background:var(--bad-bg)}.stat.bad .n{color:var(--bad)}
.stat.warn{background:var(--warn-bg)}.stat.warn .n{color:var(--warn)}
.stat.good .n{color:var(--good)}

/* ---- sites ---- */
.sites{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}
.site{display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-radius:12px;padding:11px 13px;background:#fff}
.site .nm{font-weight:600;font-size:14.5px}
.site .st{font-size:12.5px;color:var(--soft)}
.site.down{border-color:#f5c2c2;background:var(--bad-bg)}

/* ---- rows ---- */
.rows > .r{display:flex;align-items:center;gap:12px;padding:11px 18px;border-top:1px solid var(--line-2)}
.rows > .r:first-child{border-top:0}
.m{flex:1;min-width:0}
.t{font-weight:600;font-size:14.5px;overflow-wrap:anywhere}
.d{font-size:13px;color:var(--soft);overflow-wrap:anywhere}
.e{font-size:13px;color:var(--bad);margin-top:2px;overflow-wrap:anywhere}
.r .x{flex:none;display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end}
.kv{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid var(--line-2);font-size:14px}
.kv:first-child{border-top:0}
.kv > span:first-child{color:var(--soft)}
.kv > span:last-child{text-align:right}

/* ---- badges ---- */
.b{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;padding:3px 10px;border-radius:999px;
  background:var(--line-2);color:var(--soft);white-space:nowrap}
.b::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;opacity:.9}
.b.plain::before{display:none}
.b.ok{background:var(--good-bg);color:var(--good)}
.b.bad{background:var(--bad-bg);color:var(--bad)}
.b.warn{background:var(--warn-bg);color:var(--warn)}
.b.info{background:var(--navy-l);color:var(--navy)}
.dot{width:10px;height:10px;border-radius:50%;flex:none;background:var(--faint)}
.dot.ok{background:#22a35a}.dot.bad{background:var(--bad)}.dot.warn{background:#e8a317}

/* ---- controls ---- */
.btn{font-size:13.5px;font-weight:600;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:#fff;
  color:var(--ink);cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:6px}
.btn:hover{background:var(--navy-l);border-color:#cfd5f0}
.btn.pri{background:var(--navy);border-color:var(--navy);color:#fff}
.btn.pri:hover{background:var(--navy-d)}
.btn.danger{color:var(--bad);border-color:#f2c9c9}
.btn.danger:hover{background:var(--bad-bg)}
.btn.sm{padding:5px 10px;font-size:12.5px;border-radius:8px}
.btn.link{border:0;background:none;color:var(--navy);padding:4px 6px}
.btn:disabled{opacity:.5;cursor:default}
.line{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.line + .line{margin-top:8px}
input,select{font:inherit;font-size:14px;padding:8px 11px;border:1px solid var(--line);border-radius:10px;background:#fff;
  color:var(--ink);max-width:100%;min-height:38px}
input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,170,230,.15)}
input.grow{flex:1;min-width:200px}
label.lbl{font-size:13px;color:var(--soft);font-weight:600}

/* ---- people ---- */
.people{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-flex;align-items:center;gap:4px;background:var(--page);border:1px solid var(--line);border-radius:999px;
  padding:4px 4px 4px 12px;font-size:13.5px}
.chip button{border:0;background:none;color:var(--faint);font-size:17px;line-height:1;cursor:pointer;padding:0 6px;border-radius:50%}
.chip button:hover{color:var(--bad);background:var(--bad-bg)}

/* ---- folding ---- */
details.fold{border-top:1px solid var(--line-2)}
details.fold > summary{list-style:none;cursor:pointer;padding:12px 18px;font-weight:600;font-size:14px;color:var(--navy);
  display:flex;align-items:center;gap:8px}
details.fold > summary::-webkit-details-marker{display:none}
details.fold > summary::before{content:"";width:7px;height:7px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;
  transform:rotate(-45deg);transition:transform .15s;margin-right:2px}
details.fold[open] > summary::before{transform:rotate(45deg)}
details.fold > .in{padding:0 18px 14px}
details.fold > .in.flush{padding:0 0 4px}

details.site-acc{border-top:1px solid var(--line-2)}
details.site-acc:first-of-type{border-top:0}
details.site-acc > summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:13px 18px}
details.site-acc > summary::-webkit-details-marker{display:none}
details.site-acc > summary:hover{background:#fafbfd}
details.site-acc > summary .chev{width:8px;height:8px;border-right:2px solid var(--faint);border-bottom:2px solid var(--faint);
  transform:rotate(-45deg);transition:transform .15s;flex:none}
details.site-acc[open] > summary .chev{transform:rotate(45deg)}
details.site-acc > .in{padding:4px 18px 16px 38px}
.opts{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line)}

/* ---- tables ---- */
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:12px;font-weight:600;color:var(--soft);padding:9px 12px;border-bottom:1px solid var(--line);
  background:#fafbfd;white-space:nowrap}
td{padding:10px 12px;border-bottom:1px solid var(--line-2);vertical-align:top}
tr:last-child td{border-bottom:0}
td.c,th.c{text-align:center}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px;overflow-wrap:anywhere}
.muted{color:var(--soft);font-size:13px}
.empty{color:var(--faint);font-size:14px;padding:14px 18px}

/* ---- settings ---- */
.set{display:grid;grid-template-columns:1fr minmax(160px,260px) auto;gap:6px 14px;align-items:center;padding:13px 18px;
  border-top:1px solid var(--line-2)}
.set:first-child{border-top:0}
.set .what{font-size:14.5px;font-weight:600}
.set .nm{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--faint);overflow-wrap:anywhere}
.set input,.set select{width:100%}

/* ---- messages ---- */
.err{background:var(--bad-bg);color:var(--bad);border-radius:10px;padding:10px 14px;font-size:13.5px;margin:12px 18px}
.note{background:var(--warn-bg);color:#6b4500;border-radius:10px;padding:10px 14px;font-size:13.5px;margin:12px 18px}
.help{color:var(--soft);font-size:13px;margin:10px 0 0}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:28px;z-index:50;background:var(--ink);color:#fff;
  padding:11px 18px;border-radius:12px;font-size:14px;display:none;max-width:92vw;box-shadow:0 10px 30px rgba(0,0,0,.25)}
#toast.bad{background:var(--bad)}
.loading{display:flex;align-items:center;gap:10px;color:var(--soft);padding:30px 0}
.spin{display:inline-block;width:18px;height:18px;border:2px solid var(--line);border-top-color:var(--navy);border-radius:50%;
  animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.day{font-size:12px;font-weight:700;color:var(--faint);text-transform:uppercase;letter-spacing:.06em;padding:12px 18px 4px;
  background:#fafbfd;border-top:1px solid var(--line-2)}
.day:first-child{border-top:0}

nav.tabs{display:none}
@media (max-width:820px){
  nav.side{display:none}
  main{padding:16px 14px 104px}
  .ph h1{font-size:21px}
  nav.tabs{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:30;background:#fff;border-top:1px solid var(--line);
    overflow-x:auto;padding:6px 6px calc(6px + env(safe-area-inset-bottom));gap:2px;scrollbar-width:none}
  nav.tabs a{flex-direction:column;gap:3px;font-size:11px;padding:6px 8px;min-width:70px;justify-content:center;text-align:center;margin:0}
  nav.tabs a.on{background:var(--navy-l);color:var(--navy)}
  nav.tabs a .flag{position:absolute;margin:0 0 0 22px}
  #toast{bottom:84px}
  header .who small,header .hb span{display:none}
  .cols{grid-template-columns:1fr}
  .set{grid-template-columns:1fr;gap:6px}
  .rows > .r{flex-wrap:wrap}
  details.site-acc > .in{padding-left:18px}
  th,td{padding:8px}
}
</style></head>
<body>
<header>
  <span class="plate"><img src="/images/titan-energy-helmet.png" alt=""></span>
  <div class="who"><b>Titan Admin</b><small id="who"></small></div>
  <span class="sp"></span>
  <button class="hb" onclick="load()" title="Refresh this section"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg><span>Refresh</span></button>
  <button class="hb" onclick="location.href='/'" title="Back to the intranet"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg><span>Intranet</span></button>
</header>
<div class="wrap">
  <nav class="side" id="side"></nav>
  <main id="main"><div class="loading"><span class="spin"></span>Loading…</div></main>
</div>
<nav class="tabs" id="tabs"></nav>
<div id="toast" role="status" aria-live="polite"></div>
<script>
const ME = __ME__;
const I = {
  overview:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  access:'<circle cx="9" cy="8" r="4"/><path d="M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7"/><path d="M17 11l2 2 4-4"/>',
  settings:'<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  work:'<path d="M4 5h16v14H4z"/><path d="M4 7l8 6 8-6"/>',
  restore:'<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
  database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>'
};
const SECTIONS = [
  ['overview','Overview','How every site is doing right now.'],
  ['access','Access','Who can open which site.'],
  ['settings','Settings','The switches each site runs on.'],
  ['work','Scans & mail','Ticket scans being read, and the mailboxes being checked.'],
  ['restore','Restore','Put back things that were cleared out. Nothing here deletes anything.'],
  ['database','Database','The shared database every site uses.'],
  ['activity','Activity','What changed recently.']
];
let cur = (location.hash || '#overview').slice(1);
if(!SECTIONS.some(s => s[0] === cur)) cur = 'overview';
let FLAG = false;               /* the overview found something wrong */
document.getElementById('who').textContent = ME.name || ME.email;

/* ---- helpers ---- */
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const q = s => esc(JSON.stringify(String(s == null ? '' : s)));   /* a JS string, safe inside onclick="" */
const icon = k => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + I[k] + '</svg>';
const list = x => Array.isArray(x) ? x : [];
const num = n => n == null ? '0' : Number(n).toLocaleString();
function ago(t){
  if(!t) return 'never';
  const s = (Date.now() - new Date(t).getTime()) / 1000;
  if(isNaN(s)) return esc(t);
  if(s < 0) return s > -5400 ? 'in ' + Math.round(-s / 60) + ' min' : 'in ' + Math.round(-s / 3600) + ' h';
  if(s < 90) return 'just now';
  if(s < 5400) return Math.round(s / 60) + ' min ago';
  if(s < 172800) return Math.round(s / 3600) + ' hours ago';
  return Math.round(s / 86400) + ' days ago';
}
function when(t){ if(!t) return ''; const d = new Date(t); return isNaN(d) ? esc(t) : d.toLocaleString([], {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}); }
function dayOf(t){
  const d = new Date(t); if(isNaN(d)) return 'Earlier';
  const a = new Date(); a.setHours(0,0,0,0);
  const diff = Math.round((a - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  return diff === 0 ? 'Today' : diff === 1 ? 'Yesterday' : d.toLocaleDateString([], {weekday:'long', month:'short', day:'numeric'});
}
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
const failed = x => x && !Array.isArray(x) && x.error;
function errBox(x, what){ return failed(x) ? '<div class="err">' + (what ? 'Couldn\'t read ' + what + ': ' : '') + esc(x.error) + '</div>' : ''; }
const badge = (tone, text) => '<span class="b ' + (tone || '') + '">' + text + '</span>';
const stat = (n, label, sub, tone) => '<div class="stat ' + (tone || '') + '"><div class="n">' + n + '</div><div class="l">' + label + '</div>' + (sub ? '<div class="s">' + sub + '</div>' : '') + '</div>';
const card = (title, body, right, sub) => '<div class="card"><div class="ch"><h2>' + title + (sub ? '<span class="sub">' + sub + '</span>' : '') + '</h2>' + (right || '') + '</div>' + body + '</div>';
const row = (t, d, x, e) => '<div class="r"><div class="m"><div class="t">' + t + '</div>' + (d ? '<div class="d">' + d + '</div>' : '') + (e ? '<div class="e">' + e + '</div>' : '') + '</div>' + (x ? '<div class="x">' + x + '</div>' : '') + '</div>';
const kv = (k, v) => '<div class="kv"><span>' + k + '</span><span>' + v + '</span></div>';
const fold = (label, inner, flush, open) => '<details class="fold"' + (open ? ' open' : '') + '><summary>' + label + '</summary><div class="in' + (flush ? ' flush' : '') + '">' + inner + '</div></details>';
const empty = t => '<div class="empty">' + t + '</div>';

/* ---- navigation ---- */
function nav(){
  const h = SECTIONS.map(([k, l]) => '<a class="' + (k === cur ? 'on' : '') + '" onclick="go(\'' + k + '\')">' + icon(k) + '<span>' + l + '</span>'
    + (k === 'overview' && FLAG ? '<span class="flag" title="Something needs attention"></span>' : '') + '</a>').join('');
  document.getElementById('side').innerHTML = h; document.getElementById('tabs').innerHTML = h;
}
function go(k){ cur = k; history.replaceState(null, '', '#' + k); nav(); load(); window.scrollTo(0, 0); }
function head(){ const s = SECTIONS.find(x => x[0] === cur); return '<div class="ph"><h1>' + s[1] + '</h1><p>' + s[2] + '</p></div>'; }
async function load(){
  const m = document.getElementById('main');
  if(!m.querySelector('.ph')) m.innerHTML = head() + '<div class="loading"><span class="spin"></span>Loading…</div>';
  else m.style.opacity = '.6';
  try{ await R[cur](m); }catch(e){ m.innerHTML = head() + '<div class="card"><div class="err">' + esc(e.message) + '</div></div>'; }
  m.style.opacity = '';
}
const R = {};

/* ---- overview ---------------------------------------------------------- */
R.overview = async m => {
  const j = await api('overview');
  const t = j.tickets || {}, a = j.ap || {}, d = j.dispatch || {}, db = j.database || {};
  const st = failed(t) ? {} : Object.fromEntries(list(t.jobs).map(r => [r.state, r.n]));
  const tankAge = d.tanks && d.tanks.age_s;

  /* what needs attention, in plain words, each pointing at where it is fixed */
  const issues = [];
  list(j.sites).forEach(s => { if(!s.ok) issues.push([esc(s.name) + ' is not answering' + (s.status ? ' (error ' + s.status + ')' : ''), null]); });
  if(!failed(t) && t.mail && t.mail.ok === false) issues.push(['The ticket mailbox check is failing', 'work']);
  if(st.failed) issues.push([st.failed + ' ticket scan' + (st.failed === 1 ? '' : 's') + ' could not be read in the last 24 hours', 'work']);
  if(!failed(a)) list(a.mailboxes).forEach(b => { if(b.last && b.last.ok === false) issues.push(['The AP mailbox ' + esc(b.mailbox) + ' is not being read', 'work']); });
  if(!failed(d) && tankAge > 7200) issues.push(['No new tank readings for ' + Math.round(tankAge / 3600) + ' hours', null]);
  if(!failed(db) && db.stuck) issues.push([db.stuck + ' database connection' + (db.stuck === 1 ? ' is' : 's are') + ' stuck', 'database']);
  [[t, 'ticket'], [a, 'AP'], [d, 'dispatch'], [db, 'database']].forEach(([x, n]) => { if(failed(x)) issues.push(['Couldn\'t read the ' + n + ' figures', null]); });
  FLAG = issues.length > 0; nav();

  let h = head();
  h += issues.length
    ? '<div class="banner bad"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17.5v.5"/></svg><div><p class="big">'
      + issues.length + ' thing' + (issues.length === 1 ? ' needs' : 's need') + ' attention</p><ul>'
      + issues.map(([txt, where]) => '<li>' + txt + (where ? ' &mdash; <a onclick="go(\'' + where + '\')" href="#' + where + '">look</a>' : '') + '</li>').join('') + '</ul></div></div>'
    : '<div class="banner ok"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.5l3 3 6-6.5"/></svg><div><p class="big">Everything is running</p>'
      + '<div style="font-size:13.5px">Checked ' + when(j.at) + '.</div></div></div>';

  h += card('Sites', '<div class="cb"><div class="sites">' + list(j.sites).map(s => '<div class="site' + (s.ok ? '' : ' down') + '"><span class="dot ' + (s.ok ? 'ok' : 'bad') + '"></span><div><div class="nm">'
      + esc(s.name) + '</div><div class="st">' + (s.ok ? 'Up' + (s.ms ? ' · ' + s.ms + ' ms' : '') : 'Down' + (s.status ? ' · error ' + s.status : '')) + '</div>'
      + (!s.ok && typeof s.detail === 'string' ? '<div class="st">' + esc(s.detail) + '</div>' : '') + '</div></div>').join('') + '</div></div>');

  h += '<div class="cols">';
  /* tickets */
  let tb = errBox(t, 'the ticket figures');
  if(!failed(t)){
    const tray = (t.tray && t.tray.n) || 0;
    tb += '<div class="cb"><div class="stats">'
      + stat(num(tray), 'Scans waiting to be sorted', t.tray && t.tray.oldest ? 'oldest ' + ago(t.tray.oldest) : '')
      + stat(num((st.queued || 0) + (st.running || 0)), 'Being read now', st.running ? st.running + ' running' : '')
      + stat(num(st.done || 0), 'Read today', 'last 24 hours', 'good')
      + stat(num(st.failed || 0), 'Couldn\'t be read', st.failed ? '<a onclick="go(\'work\')" href="#work">see which</a>' : '', st.failed ? 'bad' : '')
      + '</div></div><div class="cb" style="padding-top:0">'
      + kv('Mailbox check', t.mail ? (t.mail.ok ? badge('ok', 'Working') : badge('bad', 'Failing')) + ' <span class="muted">' + ago(t.mail.checked_at) + '</span>' : '<span class="muted">not checked yet</span>')
      + kv('Last batch', t.last_batch ? esc(t.last_batch.batch_id) + ' <span class="muted">' + ago(t.last_batch.added_at) + '</span>' : '<span class="muted">none</span>')
      + '</div>';
  }
  h += card('Tickets', tb, '<button class="btn sm" onclick="act(\'work/run-now\', {}, \'Asked the ticket worker to check mail now\')">Check mail now</button>');

  /* AP */
  let ab = errBox(a, 'the AP figures');
  if(!failed(a)){
    const w = a.waiting || {};
    ab += '<div class="cb"><div class="stats">' + stat(num(w.to_review), 'Invoices to review') + stat(num(w.ready_for_qb), 'Ready for QuickBooks', '', w.ready_for_qb ? 'good' : '')
      + stat(num(w.tray), 'In the sorting tray') + '</div></div>';
    ab += '<div class="rows">' + list(a.mailboxes).map(b => { const l = b.last || {};
      return row(esc(b.mailbox), l.at ? 'checked ' + ago(l.at) : 'never checked', l.at ? (l.ok === false ? badge('bad', 'Not working') : badge('ok', 'Working')) : badge('', 'Unknown'),
        l.ok === false && l.error ? esc(l.error) : ''); }).join('') + '</div>';
  }
  h += card('Accounts payable', ab);

  /* dispatch */
  let dbx = errBox(d, 'the dispatch figures');
  if(!failed(d)){
    dbx += '<div class="cb">'
      + kv('Last tank reading', d.tanks && d.tanks.last_stored ? badge(tankAge > 7200 ? 'warn' : 'ok', ago(d.tanks.last_stored)) : '<span class="muted">none</span>')
      + kv('Last sent to the board', d.board_push ? esc(d.board_push.batch_id) + ' <span class="muted">' + ago(d.board_push.pushed_at) + '</span>' : '<span class="muted">none</span>')
      + '</div>';
  }
  h += card('Dispatch', dbx);

  /* database */
  let ddb = errBox(db, 'the database');
  if(!failed(db)){
    ddb += '<div class="cb"><div class="stats">' + stat(esc(db.size || '?'), 'Size') + stat(num(db.connections), 'Connections')
      + stat(num(db.stuck || 0), 'Stuck', db.stuck ? '<a onclick="go(\'database\')" href="#database">sort it out</a>' : '', db.stuck ? 'warn' : '') + '</div></div>';
  }
  h += card('Database', ddb);
  h += '</div>';
  m.innerHTML = h;
};

/* ---- access ------------------------------------------------------------ */
const OPEN = new Set();          /* which sites are unfolded, kept across reloads */
function remember(el, slug){ if(el.open) OPEN.add(slug); else OPEN.delete(slug); }
R.access = async m => {
  const j = await api('access');
  let h = head();
  let sb = errBox(j.sites, 'the sites');
  sb += list(j.sites).map(s => {
    const people = s.people || [], slug = s.slug;
    const tags = (s.live === false ? badge('bad', 'Turned off') : '') + (s.open_to_all ? badge('warn', 'Everyone at Titan') : '');
    return '<details class="site-acc"' + (OPEN.has(slug) ? ' open' : '') + ' ontoggle="remember(this,' + q(slug) + ')"><summary><span class="chev"></span>'
      + '<div class="m"><div class="t">' + esc(s.name || slug) + '</div><div class="d mono">' + esc(s.url || slug) + '</div></div>'
      + tags + badge('plain', s.open_to_all ? 'Open' : people.length + ' ' + (people.length === 1 ? 'person' : 'people')) + '</summary><div class="in">'
      + (people.length ? '<div class="people">' + people.map(p => '<span class="chip" title="Given by ' + esc(p.granted_by || '?') + (p.granted_at ? ', ' + when(p.granted_at) : '') + '">'
          + esc(p.email) + '<button onclick="revoke(' + q(slug) + ',' + q(p.email) + ')" aria-label="Remove ' + esc(p.email) + '">&times;</button></span>').join('') + '</div>'
        : '<p class="muted" style="margin:0">' + (s.open_to_all ? 'Open to everyone at Titan, so nobody needs adding.' : 'Nobody has access yet.') + '</p>')
      + '<div class="line" style="margin-top:12px"><input class="grow" id="g_' + esc(slug) + '" placeholder="name@tetransports.com — several at once is fine" onkeydown="if(event.key===\'Enter\')grant(' + q(slug) + ')">'
      + '<button class="btn pri" onclick="grant(' + q(slug) + ')">Give access</button></div>'
      + '<div class="opts"><div class="lbl" style="margin-bottom:8px">Site options</div><div class="line">'
      + '<input id="n_' + esc(slug) + '" value="' + esc(s.name || '') + '" placeholder="Name">'
      + '<input class="grow" id="u_' + esc(slug) + '" value="' + esc(s.url || '') + '" placeholder="https://…">'
      + '<button class="btn" onclick="siteSave(' + q(slug) + ')">Save</button></div><div class="line">'
      + '<button class="btn" onclick="siteFlag(' + q(slug) + ',\'live\',' + (s.live === false) + ')">' + (s.live === false ? 'Turn back on' : 'Turn off (hides its tile)') + '</button>'
      + '<button class="btn ' + (s.open_to_all ? '' : 'danger') + '" onclick="siteFlag(' + q(slug) + ',\'open_to_all\',' + !s.open_to_all + ')">'
      + (s.open_to_all ? 'Limit to the people listed' : 'Open to everyone at Titan') + '</button>'
      + '<span class="muted">Short name: <span class="mono">' + esc(slug) + '</span></span></div></div></div></details>';
  }).join('');
  sb += fold('Add a site', '<div class="line"><input id="ns_slug" placeholder="Short name, e.g. titan-bids"><input id="ns_name" placeholder="Name">'
    + '<input class="grow" id="ns_url" placeholder="https://…"><button class="btn pri" onclick="addSite()">Add</button></div>'
    + '<p class="help">The short name is what the app is set up with (SITE_SLUG) and can\'t be changed later.</p>');
  h += card('Sites', '<div>' + sb + '</div>', '', 'click one to see and change who is on it');

  /* admins */
  const pa = list(j.portal_admins);
  let ad = '<div class="cb">'
    + kv('Can open this admin page', esc(list(j.admin_site_users).join(', ') || 'nobody'))
    + kv('Always let into every site', esc(list(j.breakglass).join(', ') || 'nobody'))
    + '<p class="help" style="margin-top:4px">These two are set in Azure (ADMIN_SITE_USERS and PORTAL_ADMINS), not here.</p></div>'
    + '<div class="cb" style="border-top:1px solid var(--line-2)"><div class="lbl" style="margin-bottom:8px">Portal admins</div>'
    + (pa.length ? '<div class="people">' + pa.map(p => '<span class="chip">' + esc(p.email)
        + '<button onclick="paRemove(' + q(p.email) + ')" aria-label="Remove">&times;</button></span>').join('') + '</div>' : '<p class="muted" style="margin:0">None.</p>')
    + errBox(j.portal_admins)
    + '<div class="line" style="margin-top:12px"><input class="grow" id="pa_new" placeholder="name@tetransports.com"><button class="btn" onclick="paAdd()">Add portal admin</button></div></div>';
  h += card('Admins', ad);

  /* intranet groups */
  const it = j.intranet || {};
  let gb = errBox(it, 'the intranet groups');
  if(!failed(it)){
    const gs = it.groups || [];
    gb += '<div class="tw"><table><tr><th>Person</th>' + gs.map(g => '<th class="c">' + esc(g.label || g.name) + '</th>').join('') + '</tr>'
      + (it.members || []).map(p => '<tr><td>' + esc(p.email) + '</td>' + gs.map(g => '<td class="c"><input type="checkbox" '
        + (p.groups.includes(g.name) ? 'checked ' : '') + 'onchange="setGroups(this,' + q(p.email) + ')" data-g="' + esc(g.name) + '" aria-label="' + esc(g.label || g.name) + '"></td>').join('') + '</tr>').join('')
      + '</table></div><div class="cb" style="border-top:1px solid var(--line-2)"><div class="line"><input class="grow" id="ig_new" placeholder="name@tetransports.com"><select id="ig_g">'
      + gs.map(g => '<option value="' + esc(g.name) + '">' + esc(g.label || g.name) + '</option>').join('') + '</select>'
      + '<button class="btn" onclick="igAdd()">Add to group</button></div></div>';
  }
  h += card('Intranet groups', gb, '', 'which intranet sections each person sees');
  m.innerHTML = h;
};
function grant(slug){ const v = document.getElementById('g_' + slug).value; if(!v.trim()) return; OPEN.add(slug); act('access/grant', {slug, emails: v}, 'Access given'); }
function revoke(slug, email){ if(confirm('Take ' + email + ' off ' + slug + '?')) act('access/revoke', {slug, email}, 'Removed'); }
function siteSave(slug){ act('access/site', {slug, name: document.getElementById('n_' + slug).value, url: document.getElementById('u_' + slug).value}, 'Saved'); }
function siteFlag(slug, k, v){
  const b = {slug}; b[k] = v;
  if(k === 'open_to_all' && v){ const c = prompt('This lets EVERYONE at Titan into ' + slug + '. Type ' + slug + ' to confirm.'); if(!c) return; b.confirm = c; }
  act('access/site', b, 'Saved');
}
function addSite(){ act('access/site', {new: true, slug: document.getElementById('ns_slug').value, name: document.getElementById('ns_name').value, url: document.getElementById('ns_url').value}, 'Site added'); }
function paAdd(){ act('access/portal-admin', {email: document.getElementById('pa_new').value}, 'Added'); }
function paRemove(email){ if(confirm('Remove ' + email + ' as a portal admin?')) act('access/portal-admin', {email, remove: true}, 'Removed'); }
function igAdd(){ act('access/intranet', {email: document.getElementById('ig_new').value, groups: [document.getElementById('ig_g').value]}, 'Added'); }
function setGroups(box, email){
  const groups = [...box.closest('tr').querySelectorAll('input[type=checkbox]')].filter(x => x.checked).map(x => x.dataset.g);
  act('access/intranet', {email, groups}, 'Saved', false);
}

/* ---- settings (Azure) -------------------------------------------------- */
let AZ = null, AZAPP = null;
R.settings = async m => {
  const j = AZ || await api('azure/apps');
  let h = head();
  if(j.missing){
    h += '<div class="card"><div class="note" style="margin:16px 18px"><b>Not connected to Azure yet.</b> The page needs its own Azure login before it can change settings. '
      + 'Missing on the intranet app: <b>' + esc(j.missing.join(', ')) + '</b>. The steps are in <b>Admin site - walkthrough.md</b> in the Intranet folder.</div></div>';
    h += switchList(j.switches || [], null, {});
    m.innerHTML = h; return;
  }
  AZ = j;
  const apps = j.apps || [];
  if(!AZAPP || !apps.some(a => a.name === AZAPP)) AZAPP = (apps.find(a => /tickets$/.test(a.name)) || apps[0] || {}).name;
  const app = apps.find(a => a.name === AZAPP) || {};
  const picker = '<div class="card"><div class="cb"><div class="line"><label class="lbl" for="azapp">Web app</label><select id="azapp" onchange="AZAPP=this.value;load()" style="flex:1;min-width:200px">'
    + apps.map(a => '<option value="' + esc(a.name) + '"' + (a.name === AZAPP ? ' selected' : '') + '>' + esc(a.name) + (a.state && a.state !== 'Running' ? ' (' + esc(a.state) + ')' : '') + '</option>').join('')
    + '</select><button class="btn danger" onclick="restartApp()">Restart app</button></div>'
    + '<p class="help">' + esc((app.hosts || []).join(' · ')) + (app.hosts && app.hosts.length ? ' — ' : '') + 'Saving any setting restarts the app for about 30 seconds.</p></div></div>';
  h += picker;
  m.innerHTML = h + '<div class="loading"><span class="spin"></span>Reading settings…</div>';
  const s = await api('azure/settings?app=' + encodeURIComponent(AZAPP));
  const by = Object.fromEntries(s.settings.map(x => [x.name, x]));
  h += switchList(j.switches || [], AZAPP, by);
  h += '<div class="card">' + fold('Show every setting on ' + esc(AZAPP) + ' (' + s.settings.length + ')',
      '<div style="padding:0 18px 6px">' + (s.test_target ? '<div class="note" style="margin:0 0 10px">This is a test app or slot. It will refuse a database setting that matches production\'s.</div>' : '')
      + '<p class="help" style="margin:0">Secrets show only as "set" and can be replaced, never read. Guarded ones need the app\'s name typed to change.</p></div>'
      + s.settings.map(x => setRow(x)).join('')
      + '<div class="set"><input id="new_n" placeholder="NEW_SETTING_NAME"><input id="new_v" placeholder="value">'
      + '<button class="btn pri" onclick="setVal(document.getElementById(\'new_n\').value, document.getElementById(\'new_v\').value)">Add setting</button></div>', true)
    + '</div>';
  m.innerHTML = h;
};
function setRow(x){
  const id = 'v_' + x.name;
  return '<div class="set"><div><div class="mono" style="color:var(--ink);font-size:13px">' + esc(x.name) + '</div>'
    + (x.guarded ? badge('warn', 'Guarded') : '') + (x.secret ? ' ' + badge('info', 'Secret') : '') + '</div>'
    + (x.secret ? '<input id="' + esc(id) + '" type="password" placeholder="' + esc(x.hint) + ' — type to replace" autocomplete="new-password">'
              : '<input id="' + esc(id) + '" value="' + esc(x.value) + '">')
    + '<div class="line"><button class="btn sm" onclick="setVal(' + q(x.name) + ', document.getElementById(' + q(id) + ').value, ' + !!x.guarded + ', ' + !!x.secret + ')">Save</button>'
    + '<button class="btn sm danger" onclick="delVal(' + q(x.name) + ', ' + !!x.guarded + ')" title="Delete this setting">Delete</button></div></div>';
}
function switchList(sw, app, by){
  const sites = [...new Set(sw.map(s => s.site))];
  let h = '';
  sites.forEach(site => {
    let rows = '';
    sw.filter(s => s.site === site).forEach(s => {
      const have = by[s.name], v = have ? (have.secret ? '' : have.value) : '';
      let ctl;
      if(!app) ctl = '<span></span>';
      else if(s.kind === 'choice') ctl = '<select id="sw_' + s.name + '"><option value="">(not set)</option>' + s.choices.map(c => '<option' + (c === v ? ' selected' : '') + '>' + esc(c) + '</option>').join('') + '</select>';
      else if(s.kind === 'bool') ctl = '<select id="sw_' + s.name + '"><option value="">(not set)</option><option value="1"' + (/^(1|true|on|yes)$/i.test(v) ? ' selected' : '') + '>On</option><option value="0"' + (/^(0|false|off|no)$/i.test(v) ? ' selected' : '') + '>Off</option></select>';
      else ctl = '<input id="sw_' + s.name + '" value="' + esc(v) + '"' + (s.kind === 'number' ? ' inputmode="numeric"' : '') + ' placeholder="(not set)">';
      rows += '<div class="set"><div><div class="what">' + esc(s.help) + '</div><div class="nm">' + esc(s.name) + (app && !have ? ' · not set on this app' : '') + '</div></div>' + ctl
        + (app ? '<button class="btn sm" onclick="setVal(' + q(s.name) + ', document.getElementById(' + q('sw_' + s.name) + ').value, ' + (s.name === 'PORTAL_ADMINS') + ')">Save</button>' : '<span></span>') + '</div>';
    });
    h += card(esc(site === 'All' ? 'Every site' : site), '<div>' + rows + '</div>', '', app ? '' : 'for reference until Azure is connected');
  });
  return h;
}
async function setVal(name, value, guarded, secret){
  name = (name || '').trim(); if(!name) return;
  if(secret && !value){ toast('Type the new value first', true); return; }
  let confirmName = '';
  if(guarded){ confirmName = prompt(name + ' is guarded. Type the app name (' + AZAPP.split('/')[0] + ') to change it.'); if(!confirmName) return; }
  else if(!confirm('Set ' + name + ' on ' + AZAPP + '? The app restarts for about 30 seconds.')) return;
  await act('azure/set', {app: AZAPP, name, value, confirm: confirmName}, name + ' saved — ' + AZAPP + ' is restarting');
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

/* ---- scans & mail ------------------------------------------------------ */
const STATE = {queued: ['', 'Waiting'], running: ['warn', 'Reading'], done: ['ok', 'Done'], failed: ['bad', 'Failed'], cancelled: ['', 'Cancelled']};
function jobRow(x){
  const s = STATE[x.state] || ['', esc(x.state)];
  const btns = (x.state === 'failed' || x.state === 'cancelled' ? '<button class="btn sm" onclick="act(\'work/job\', {id:' + x.id + ', action:\'retry\'}, \'Queued again\')">Try again</button>' : '')
    + (x.state === 'queued' ? '<button class="btn sm" onclick="act(\'work/job\', {id:' + x.id + ', action:\'now\'}, \'Runs on the next tick\')">Run now</button>'
      + '<button class="btn sm danger" onclick="if(confirm(\'Cancel job ' + x.id + '?\')) act(\'work/job\', {id:' + x.id + ', action:\'cancel\'}, \'Cancelled\')">Cancel</button>' : '');
  return row(esc(x.batch_id || x.subject || x.kind) + ' <span class="muted" style="font-weight:400">#' + x.id + '</span>',
    when(x.finished_at || x.started_at || x.queued_at) + (x.pages_total ? ' · ' + x.pages_done + ' of ' + x.pages_total + ' pages' : '')
      + (x.state === 'queued' && x.run_after ? ' · runs ' + when(x.run_after) : ''),
    badge(s[0], s[1]) + btns, x.error ? esc(x.error) : '');
}
R.work = async m => {
  const j = await api('work');
  let h = head();
  /* worker */
  let wb = errBox(j.mail, 'the ticket mailbox');
  if(j.mail && !failed(j.mail)) wb += '<div class="rows">' + row('Ticket mailbox', 'checked ' + ago(j.mail.checked_at) + (j.mail.waiting != null ? ' · ' + j.mail.waiting + ' emails waiting' : ''),
    j.mail.ok ? badge('ok', 'Working') : badge('bad', 'Failing')) + list(j.requests).map(r => row('Asked to ' + esc(r.kind === 'poll' ? 'check mail' : r.kind === 'run' ? 'run the queue' : r.kind),
      'by ' + esc(r.asked_by || '?') + ' ' + ago(r.asked_at), r.taken_at ? badge('ok', 'Picked up ' + ago(r.taken_at)) : badge('warn', 'Not picked up yet'))).join('') + '</div>';
  h += card('Ticket worker', wb, '<button class="btn sm pri" onclick="act(\'work/run-now\', {}, \'Asked — the worker picks it up within a minute\')">Check mail now</button>');

  /* jobs */
  const jobs = list(j.jobs);
  const bad = jobs.filter(x => x.state === 'failed'), live = jobs.filter(x => x.state === 'queued' || x.state === 'running'),
        rest = jobs.filter(x => !['failed', 'queued', 'running'].includes(x.state));
  let jb = errBox(j.jobs, 'the reading queue');
  if(!failed(j.jobs)){
    jb += bad.length ? '<div class="day">Couldn\'t be read</div><div class="rows">' + bad.map(jobRow).join('') + '</div>' : '';
    jb += live.length ? '<div class="day">Waiting or being read</div><div class="rows">' + live.map(jobRow).join('') + '</div>' : '';
    if(!bad.length && !live.length) jb += empty('Nothing waiting and nothing failed.');
    if(rest.length) jb += fold('Show finished (' + rest.length + ')', '<div class="rows">' + rest.map(jobRow).join('') + '</div>', true);
  }
  h += card('Scans being read', jb, '', 'the last 40');

  /* tray */
  const tray = list(j.tray), disc = list(j.discarded);
  let tr = errBox(j.tray, 'the tray');
  if(!failed(j.tray)) tr += tray.length ? '<div class="rows">' + tray.map(p => row(esc(p.filename || ('Scan #' + p.id)), p.tickets + ' tickets · came in ' + ago(p.created_at))).join('') + '</div>' : empty('The tray is empty.');
  tr += fold('Discarded scans — put one back (' + disc.length + ')', failed(j.discarded) ? errBox(j.discarded) : disc.length ? '<div class="rows">' + disc.map(p => row(esc(p.filename || ('Scan #' + p.id)),
    'discarded by ' + esc(p.resolved_by || '?') + ' ' + ago(p.resolved_at), '<button class="btn sm" onclick="act(\'work/packet-restore\', {id:' + p.id + '}, \'Back in the tray\')">Back to tray</button>')).join('') + '</div>' : empty('None.'), true);
  h += card('Scans waiting to be sorted', tr, '', tray.length ? tray.length + ' in the tray' : '');

  /* AP mailboxes */
  let mb = errBox(j.ap_mailboxes, 'the AP mailboxes');
  mb += '<div class="rows">' + list(j.ap_mailboxes).map(b => { const l = b.last || {};
    return row(esc(b.mailbox), (l.at ? 'checked ' + ago(l.at) : 'never checked') + (b.reading_from ? ' · reading mail from ' + when(b.reading_from) : ''),
      (l.ok === false ? badge('bad', 'Not working') : l.at ? badge('ok', 'Working') : '')
      + '<select id="rr_' + esc(b.mailbox) + '" aria-label="Look back to"><option value="2">2 hours ago</option><option value="24">yesterday</option><option value="72">3 days ago</option><option value="168">a week ago</option></select>'
      + '<button class="btn sm" onclick="reread(' + q(b.mailbox) + ')">Read again from then</button>', l.error ? esc(l.error) : ''); }).join('') + '</div>';
  mb += '<div class="cb" style="padding-top:4px"><p class="help" style="margin:0">Reading again never files an email twice: ones already taken are skipped.</p></div>';
  const probs = list(j.ap_problems);
  mb += fold('Emails that failed or were left out (' + probs.length + ')', failed(j.ap_problems) ? errBox(j.ap_problems) : probs.length ? '<div class="rows">' + probs.map(p => row(esc(p.note), ago(p.seen_at),
    '<button class="btn sm" onclick="act(\'work/ap-forget\', {message_id: ' + q(p.message_id) + '}, \'It is read again on the next check\')">Read it again</button>')).join('') + '</div>' : empty('None.'), true);
  h += card('AP mailboxes', mb);
  m.innerHTML = h;
};
function reread(box){ const hrs = document.getElementById('rr_' + box).value; act('work/ap-reread', {mailbox: box === '(main mailbox)' ? '' : box, hours: +hrs}, 'The next check looks back from then'); }

/* ---- restore ----------------------------------------------------------- */
R.restore = async m => {
  const j = await api('restore');
  let h = head();
  let bb = errBox(j.ap_backups, 'the backups'), any = false;
  bb += '<div class="rows">';
  list(j.ap_backups).forEach(b => (b.sets || []).forEach(s => { any = true;
    bb += row((s.set === 'tray' ? 'Sorting tray' : 'Invoices') + ' — ' + num(s.rows) + ' items',
      when(s.first) + ' to ' + when(s.last) + ' · <span class="mono">' + esc(b.schema) + '</span>',
      (s.already_back ? badge('info', num(s.already_back) + ' already back') : '') + '<button class="btn sm" onclick="restoreSet(' + q(b.schema) + ',' + q(s.set) + ',' + (+s.rows || 0) + ')">Put back</button>'); }));
  bb += '</div>' + (!any && !failed(j.ap_backups) ? empty('No backups.') : '');
  h += card('AP backups', bb, '', 'taken before each clean-out');
  const v = list(j.ap_voided);
  h += card('Voided AP invoices', errBox(j.ap_voided, 'the voided invoices') + (v.length ? '<div class="rows">' + v.map(b => row(esc(b.vendor || 'No vendor') + ' · ' + esc(b.bill_number || ('#' + b.id))
      + (b.total != null ? ' · $' + Number(b.total).toFixed(2) : ''), (b.note ? esc(b.note) + ' · ' : '') + 'voided ' + ago(b.updated_at),
      '<button class="btn sm" onclick="act(\'restore/ap-unvoid\', {id:' + b.id + '}, \'Reopened — it is back in review\')">Reopen</button>')).join('') + '</div>' : failed(j.ap_voided) ? '' : empty('None.')));
  m.innerHTML = h;
};
function restoreSet(schema, set, n){
  const c = prompt('Put back ' + n + ' ' + (set === 'tray' ? 'tray items' : 'invoices') + ' from ' + schema + '? Ones already there are skipped. Type restore to confirm.');
  if(c) act('restore/ap-backup', {schema, set, confirm: c}, 'Put back');
}

/* ---- database ---------------------------------------------------------- */
R.database = async m => {
  const j = await api('database');
  let h = head();
  const all = list(j.connections);
  const cs = all.filter(c => !c.system), sys = all.filter(c => c.system);
  /* Stuck means holding something: mid-change and gone quiet, or one query
     running for over five minutes. Idle for days is not stuck - an idle
     connection holds nothing - and Supabase's own are never offered at all. */
  const stuck = c => !c.system && ((c.state === 'idle in transaction' && c.for_s > 60) || (c.state === 'active' && c.for_s > 300));
  const plain = s => ({'active': 'Working', 'idle': 'Idle', 'idle in transaction': 'Stuck mid-change'}[s] || (s ? esc(s) : 'Background'));
  const dur = s => s == null ? '' : s < 120 ? s + ' s' : s < 7200 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' hours' : Math.round(s / 86400) + ' days';
  const table = (rows, ends) => '<div class="tw"><table><tr><th>App</th><th>State</th><th>For</th>' + (ends ? '<th></th>' : '') + '</tr>'
    + rows.map(c => '<tr><td>' + esc(c.app || c.who || '—') + '</td><td>' + badge(stuck(c) ? 'warn' : c.state === 'active' ? 'ok' : '', stuck(c) && c.state === 'active' ? 'Running long' : plain(c.state)) + '</td><td class="muted">'
      + dur(c.for_s) + '</td>' + (ends ? '<td style="text-align:right">'
      + (stuck(c) ? '<button class="btn sm danger" onclick="if(confirm(\'End connection ' + c.pid + '? Its unfinished work is rolled back.\')) act(\'database/end\', {pid:' + c.pid + '}, \'Ended\')">End it</button>' : '')
      + '</td>' : '') + '</tr>').join('') + '</table></div>';
  let cb = errBox(j.connections, 'the connections');
  if(!failed(j.connections)){
    const n = cs.filter(stuck).length;
    cb += '<div class="cb"><div class="stats">' + stat(cs.length, 'Our sites\' connections') + stat(cs.filter(c => c.state === 'active').length, 'Working now')
      + stat(n, 'Stuck', n ? 'safe to end' : 'nothing to do', n ? 'warn' : 'good') + '</div>'
      + '<p class="help">Idle is normal: a site keeps a connection open and reuses it. Only one marked stuck gets an End button.</p></div>';
    cb += cs.length ? table(cs, true) : empty('None open.');
    if(sys.length) cb += fold('Supabase\'s own connections (' + sys.length + ') — leave these alone', '<p class="help" style="margin:0 18px 8px">The scheduler, the API, the pooler and the file store. Idle for days is how they work.</p>' + table(sys, false), true);
    cb += fold('Show what each one is running', '<div class="tw"><table><tr><th>App</th><th>Query</th></tr>' + all.map(c => '<tr><td>' + esc(c.app || c.who || '—') + '</td><td class="mono">' + esc(c.query || '') + '</td></tr>').join('') + '</table></div>', true);
  }
  h += card('Connections', cb);

  let sz = '<div class="cols" style="padding:14px 18px">'
    + '<div><div class="lbl" style="margin-bottom:4px">By schema</div>' + errBox(j.schemas) + list(j.schemas).map(s => kv(esc(s.schema), esc(s.size))).join('') + '</div>'
    + '<div><div class="lbl" style="margin-bottom:4px">Biggest tables</div>' + errBox(j.tables) + list(j.tables).map(t => kv('<span class="mono">' + esc(t.name) + '</span>', esc(t.size))).join('') + '</div></div>';
  const heavy = '<p class="help" style="margin:0 0 8px">Where the database\'s outgoing data goes, since the counters were last reset.</p>' + errBox(j.heavy)
    + '<div class="tw"><table><tr><th>Rows</th><th>Calls</th><th>Per call</th><th>Query</th></tr>' + list(j.heavy).map(x => '<tr><td>' + num(x.rows) + '</td><td>'
      + num(x.calls) + '</td><td>' + num(x.rows_per_call) + '</td><td class="mono">' + esc(x.query) + '</td></tr>').join('') + '</table></div>';
  h += '<div class="card">' + fold('Show sizes', sz, true) + fold('Show the queries moving the most data', heavy) + '</div>';
  m.innerHTML = h;
};

/* ---- activity ---------------------------------------------------------- */
function byDay(items, rowOf){
  let out = '', last = null;
  items.forEach(x => { const d = dayOf(x.at); if(d !== last){ out += '<div class="day">' + esc(d) + '</div>'; last = d; } out += rowOf(x); });
  return out;
}
const timeOf = t => { const d = new Date(t); return isNaN(d) ? '' : d.toLocaleTimeString([], {hour:'numeric', minute:'2-digit'}); };
R.activity = async m => {
  const j = await api('activity');
  let h = head();
  const rec = list(j.recent), mine = list(j.admin_log);
  h += card('Across the sites', errBox(j.recent, 'recent changes') + (rec.length ? '<div class="rows">' + byDay(rec, x => row(esc(x.what),
      esc(x.who || ''), badge('info', esc(x.site)) + '<span class="muted">' + timeOf(x.at) + '</span>')) + '</div>' : failed(j.recent) ? '' : empty('Nothing in the last week.')),
    '', 'the last week');
  h += card('Changes made on this page', errBox(j.admin_log) + (mine.length ? '<div class="rows">' + byDay(mine, x => row(esc(x.action) + (x.target ? ' — ' + esc(x.target) : ''),
      esc(x.who) + ' · ' + esc(x.area), '<span class="muted">' + timeOf(x.at) + '</span>')) + '</div>' : failed(j.admin_log) ? '' : empty('Nothing yet.')));
  m.innerHTML = h;
};

nav(); load();
</script>
</body></html>
"""
