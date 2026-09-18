"""The proposed new front page, as data.

The intranet's front page is a filing cabinet: cards of documents, and nothing
else. The public site at tetransports.com is for people outside the company.
This is the other thing - the place employees land, where the first screen is
the company talking to its people and the files start once you scroll.

It is a MOCKUP and it says so on the page. It lives at /welcome, reachable from
the rail, so it can be looked over before it becomes the front of the site.

What is real here and what is not:

    REAL   the departments, their folders and their document counts, all
           filtered to whoever is signed in - the same filtering the intranet
           itself does, so this page cannot show somebody a document the
           intranet would hide from them
    REAL   the alerts, out of config.json
    SAMPLE the words in the welcome cards - the owner's message, employee of
           the month, the safety counter. Placeholders, written to look like
           the real thing so the shape can be judged
    SAMPLE "most opened" and "recently opened", because nothing records opens
           yet. They are drawn from the person's own visible documents so the
           lists look right, and the page marks them as samples rather than
           letting anybody believe the numbers

Making the two counted sections real needs one table and a POST when a document
is opened. That is a small job, and it is deliberately not done yet: what the
sections should contain is worth agreeing before anything starts recording what
everybody opens.
"""
import os

# The editable text. Every one of these can be overridden by a "welcome" block
# in config.json - same as everything else on this site, so the words are not
# in the code where only a deploy can change them.
DEFAULTS = {
    "greeting": "Titan Enterprises",
    "strap": "One place for the people who work here.",
    "owner": {
        "name": "Lonnie Ridenbaugh",
        "title": "President",
        "heading": "A word from Lonnie",
        "body": "[Put the owner's message here. A few sentences - what the "
                "quarter looked like, what is coming, who deserves a mention. "
                "Change it whenever there is something worth saying; an "
                "out-of-date message from the boss is worse than none.]",
        "photo": "",
    },
    "employee": {
        "heading": "Employee of the month",
        "name": "[Name]",
        "role": "[Job title]",
        "yard": "[Yard]",
        "body": "[One paragraph on why. The specific thing they did beats "
                "anything general - people can tell the difference.]",
        "photo": "",
    },
    "safety": {
        "heading": "Days without a recordable",
        "days": 0,
        "note": "[Set this from the safety board. It is the first number "
                "anybody looks at.]",
    },
    "shoutouts": {
        "heading": "Good work this week",
        "items": [
            "[Name] — [what they did, in one line]",
            "[Name] — [what they did]",
            "[Name] — [what they did]",
        ],
    },
    "dates": {
        "heading": "This month",
        "items": [
            {"when": "[Date]", "what": "[Birthday, anniversary or event]"},
            {"when": "[Date]", "what": "[Safety meeting]"},
            {"when": "[Date]", "what": "[Pay date, holiday, open enrolment]"},
        ],
    },
    "didyouknow": {
        "heading": "Worth knowing",
        "body": "[A short, useful thing. Where a form lives, a shortcut, who "
                "to ring about what. Change it often and people will read it.]",
    },
    "numbers": {
        "heading": "Titan by the numbers",
        "items": [
            {"n": "[0]", "what": "trucks on the road"},
            {"n": "7", "what": "yards"},
            {"n": "[0]", "what": "people"},
            {"n": "[0]", "what": "loads last week"},
        ],
    },
}

SHOW_FIRST = 4          # how many of a section are shown before "Show more"
SHOW_MORE = 12          # and after it


def _merge(base, over):
    """config.json wins, key by key, without losing what it does not mention."""
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def folder_url(cfg, base):
    """The SharePoint address of a department's folder."""
    site = ((cfg.get("sharepoint") or {}).get("site") or "").rstrip("/")
    if not site or not base:
        return ""
    quoted = "/".join(p.replace(" ", "%20") for p in str(base).split("/"))
    return site + "/" + quoted


def departments(cfg):
    """Every department the signed-in person can see, with a link to its folder.

    The cfg handed in here is the FILTERED one, so a department restricted on
    the Access screen is simply not in it.
    """
    out = []
    for d in cfg.get("departments") or []:
        out.append({
            "id": d.get("id") or "",
            "name": d.get("name") or "",
            "icon": d.get("icon") or "",
            "owner": d.get("owner") or "",
            "ext": d.get("ext") or "",
            "docs": len(d.get("docs") or []),
            "url": folder_url(cfg, d.get("base")),
        })
    return out


def _all_docs(cfg):
    """Every document the person can see, with the department it came from."""
    out = []
    for d in cfg.get("departments") or []:
        for doc in d.get("docs") or []:
            out.append({
                "n": doc.get("n") or "",
                "t": doc.get("t") or "",
                "dept": d.get("name") or "",
                "deptId": d.get("id") or "",
                "url": folder_url(cfg, d.get("base")),
            })
    return out


def sections(cfg):
    """The four lists under the welcome screen.

    Only the first is real. The other three are drawn from the person's own
    visible documents so the page looks like itself, and each is marked as a
    sample - a mockup that quietly invents usage figures is how a mockup ends
    up being believed.
    """
    docs = _all_docs(cfg)
    pinned = [d for d in docs if d["t"] in ("form", "pdf")][:8]

    # Deterministic slices rather than random ones: the same person sees the
    # same page twice in a row, which is what makes it possible to talk about.
    most = docs[2::5][:12]
    recent = docs[1::7][:12]
    favourites = docs[4::11][:8]

    return {
        "static": {
            "title": "Always here",
            "note": "The handful everybody needs. Set in config.json.",
            "sample": False,
            "items": pinned,
        },
        "most": {
            "title": "Most opened",
            "note": "Across the company, last 30 days.",
            "sample": True,
            "items": most,
        },
        "recent": {
            "title": "You opened recently",
            "note": "Yours alone - nobody else sees this list.",
            "sample": True,
            "items": recent,
        },
        "favourites": {
            "title": "Your favourites",
            "note": "The stars you set on any document.",
            "sample": True,
            "items": favourites,
        },
    }


def payload(cfg, viewer=None):
    """Everything the welcome page needs, from an already-filtered config."""
    welcome = _merge(DEFAULTS, cfg.get("welcome") or {})
    return {
        "viewer": viewer or {},
        "site": cfg.get("site") or {},
        "alerts": cfg.get("alerts") or [],
        "welcome": welcome,
        "departments": departments(cfg),
        "yards": [{"id": y.get("id"), "name": y.get("name")}
                  for y in (cfg.get("yards") or [])],
        "sections": sections(cfg),
        "show": {"first": SHOW_FIRST, "more": SHOW_MORE},
        "links": {
            "files": "/",
            "plan": "/fileplan",
            "mock": True,
        },
    }


def first_name(email, fallback="there"):
    """Somebody's first name out of their email, for the greeting.

    swahl@ gives "swahl", which is not a name - so it only tries when the
    address looks like first.last, and otherwise says hello without one.
    """
    local = (email or "").split("@")[0]
    if "." in local:
        first = local.split(".")[0]
        if len(first) > 1 and first.isalpha():
            return first[:1].upper() + first[1:]
    return fallback


def enabled():
    """The mockup can be turned off without a deploy."""
    return (os.environ.get("WELCOME_PAGE") or "1").strip().lower() not in (
        "0", "off", "false", "no")
