"""The electronic filing structure, as data.

TGC-SYS-EFILE-2026-01 - the Master File Plan, owned by the CFO - numbered to
the File Class index the CFO issued in October 2026 (first draft).

THE STRUCTURE LIVES IN file_number_index.csv, next to this file. It is the
CFO's index with two repairs: the blank rows are gone, and the Former Code and
Parent Class columns are written out properly - Excel had turned codes like
10-01-01 into dates (10/1/2001). Every row is one folder, and the New Folder
Path column is what the tree is built from, so a corrected draft of the index
can be dropped in as it comes and the page follows it.

    tree()      the nested structure
    payload()   everything the page needs, as one JSON-ready dict

The numbering:

    01000_File-Plan-and-Governance          File Class 1000 - a master folder
    01000-02_Naming-Conventions-...         File Class 1000-02
    08000-01-01_Application-Resume-...      File Class 8000-01-01

Master folders are written five digits wide so SharePoint sorts 2000 before
10000. The page shows the class the way the CFO writes it - 1000-02, not
01000-02.

Rows whose Entry Type is "Record template" sit under a [RECORD-ID] segment in
the index: Employee Files, Driver Qualification Files, Unit Files, Customer and
Vendor Master Files, Owned and Leased Properties, Well Files and Active
Transactions. They are not one folder each - they are the shape that gets
copied for every employee, driver, unit and so on. In SharePoint that shape
lives in the parent's _TEMPLATE_ folder, which is what [RECORD-ID] stands for.
"""
import csv
import functools
import json
import os
import re

DOC = "TGC-SYS-EFILE-2026-01"
VERSION = "1.0"
NUMBERING = "File Class index, first draft, October 2026"
ROOT = "TITAN-GROUP"
RECORD_ID = "[RECORD-ID]"

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "file_number_index.csv")


# ---------------------------------------------------------------------------
#  Section 3 - what each master folder is for, and who owns it
# ---------------------------------------------------------------------------

MASTERS = {
    "1000": ("CFO", "The rules of the system itself - file plan, naming, "
                  "retention, permissions, templates, legal holds."),
    "2000": ("Controller", "The paper-to-electronic conveyor belt. A working "
                         "area only - nothing lives here permanently."),
    "3000": ("CFO", "Entity records, intercompany agreements, contracts, "
                  "litigation, governance, restructuring."),
    "4000": ("Controller", "Financials, close, GL, AP, AR, payroll accounting, "
                         "fixed assets, budget, unit economics."),
    "5000": ("CFO", "Federal, state, local, sales and use, IFTA, 2290, "
                  "property, payroll tax, planning."),
    "6000": ("CFO", "Bank accounts, lender relationships, loan files, UCCs, "
                  "equity, treasury."),
    "7000": ("Safety / CFO", "Policies, COIs, claims, loss runs, BWC, the risk "
                           "register."),
    "8000": ("HR", "Employee files, I-9, confidential medical, benefits, "
                 "recruiting, the handbook."),
    "9000": ("Safety / DOT", "DQFs, drug and alcohol, HOS and ELD, accidents, "
                           "inspections, authority, OSHA."),
    "10000": ("Dir. Fleet Admin & Purchasing",
           "Unit files, titles, maintenance, parts, fuel, telematics, "
           "transfers."),
    "11000": ("Head of Dispatch", "Dispatch, field and run tickets, operating "
                               "reports, yards, owner-operators."),
    "12000": ("CFO", "Customer master files, rate cards, bids, revenue "
                   "reporting, marketing."),
    "13000": ("Dir. Fleet Admin & Purchasing",
            "Vendor master files, POs, quotes, subcontractors."),
    "14000": ("CFO", "Owned and leased property, yard sites, construction, "
                   "permits."),
    "15000": ("CFO", "Well files by API, ODNR and EPA, injection reporting, "
                   "landowner leases."),
    "16000": ("Technology contact", "Systems inventory, SaaS contracts, access "
                                  "management, backup, cybersecurity."),
    "17000": ("CFO", "Active deals, closed deals, pipeline, the exit-readiness "
                   "data room."),
    "18000": ("Controller", "Closed entities, superseded records, the scanned "
                          "backfile, legal hold, pending destruction."),
}

# ---------------------------------------------------------------------------
#  Section 7 - the permissions matrix
# ---------------------------------------------------------------------------

ROLES = ["Owner / President", "CFO", "Controller", "Sr. Accountant", "HR",
         "Safety / DOT", "Fleet / Purchasing", "Dispatch", "Yard Manager"]

# F = full, E = edit, R = read, "-" = no access. The tenth column is external
# and is a sentence rather than a letter, so it is kept separately.
MATRIX = {
    "1000": ("R F E R R R R R R", "none"),
    "2000": ("R F F E E E E E E", "none"),
    "3000": ("F F R - - - - - -", "Counsel: edit"),
    "4000": ("R F F E - - R - -", "CPA: read"),
    "5000": ("R F E R - - - - -", "CPA: edit"),
    "6000": ("F F E R - - - - -", "Lender: read, staged"),
    "7000": ("R F E R R E R R R", "Broker: edit"),
    "8000": ("R R - - F - - - -", "none"),
    "9000": ("R E R - R F R R R", "Auditor: read"),
    "10000": ("R E R R - R F R E", "none"),
    "11000": ("R E R R - R R F E", "none"),
    "12000": ("R F E E - - - R -", "none"),
    "13000": ("R E E E - - F - R", "none"),
    "14000": ("F F R - - - R - R", "none"),
    "15000": ("F F R - - E - - -", "Consultant: edit"),
    "16000": ("R E R - - - - - -", "MSP: full"),
    "17000": ("F F - - - - - - -", "Advisor: edit, staged"),
    "18000": ("R F F R - - - - -", "none"),
}

# ---------------------------------------------------------------------------
#  Section 7.1 - why a folder is walled off. Keyed by folder name.
# ---------------------------------------------------------------------------

WHY = {
    "8000": (
        "HR only",
        "Everything below this point is a personnel record. The whole master "
        "folder is restricted and three folders inside it are walled off "
        "again."),
    "8000-03": (
        "HR only",
        "I-9s have to be stored apart from personnel files so they can be "
        "handed to ICE without the rest of an employee's record going with "
        "them."),
    "8000-04": (
        "HR only",
        "The ADA and OSHA 1910.1020 both require medical information to sit "
        "in a separate confidential file rather than the personnel file."),
    "8000-13": (
        "HR and CFO",
        "Harassment and retaliation exposure. Who can open the folder is "
        "itself a fact a plaintiff's lawyer will ask about."),
    "9000-02": (
        "DOT / Safety and CFO",
        "49 CFR 382.401 requires secure storage with access limited to people "
        "with a need to know."),
    "7000-04-03": (
        "HR and CFO", "Contains medical information."),
    "7000-04-04": (
        "HR and CFO", "Contains medical information."),
    "4000-06": (
        "CFO, Controller and HR", "Compensation confidentiality."),
    "6000-09": (
        "Owner and CFO", "The owner's personal financial data."),
    "3000-01-08": (
        "Owner, CFO and counsel", "Trust and estate planning."),
    "3000-01-09": (
        "CFO and the KTL partner",
        "A third-party 80/20 partnership. Filing these inside Titan's general "
        "tree creates both a partnership dispute and a consolidation question "
        "at exit."),
    "17000": (
        "Owner and CFO", "Deal confidentiality and NDA obligations."),
    "11000-02-04": (
        "CFO and the KTL partner",
        "Kimberley Transport's livestock hauling. Partitioned for the same "
        "reason as KTL's entity records: it is a third-party partnership."),
}

# The record templates, keyed by File Class: the parents whose children the
# index lists under [RECORD-ID], copied once per record rather than existing
# once. The index decides which folders are template folders (Entry Type);
# this only says what each template is copied for.
#
# The entity folders under 3000-01 and the lenders under 6000-02 share one
# shape too, but each of those exists once - they are enumerated, not copied -
# and the index rightly lists them as ordinary folders.
TEMPLATE_OF = {
    "8000-01": "every employee",
    "9000-01": "every driver",
    "10000-01": "every unit",
    "12000-01": "every customer",
    "13000-01": "every vendor",
    "14000-01": "every owned property",
    "14000-02": "every leased property",
    "15000-01": "every well",
    "17000-01": "every deal",
}

ENTITIES = [
    ("TEUI", "Titan Enterprises Unlimited, Inc.",
     "Holdco - target structure (v3.1), not yet implemented"),
    ("TET", "Titan Energy Transportation LLC",
     "Active - frac and produced water hauling"),
    ("TOL", "Titan Oil LLC", "Active - crude hauling (Marathon / MPLX)"),
    ("TTI", "Titan Trucking Industries LLC",
     "Active - dump truck and MSHA, contractor ID V438"),
    ("TEL", "Titan Enterprises Leasing Co. LLC",
     "Active - equipment titling and lessor"),
    ("TREP", "Titan Real Estate Properties LLC", "Active"),
    ("TPOL", "Titan Polishing LLC (d/b/a Reflection Metal Works)", "Active"),
    ("LRLT", "Lonnie Ridenbaugh Living Trust", "Restricted access"),
    ("KTL", "Kimberley Transport LLC",
     "80/20 partnership - third party, partitioned"),
    ("TGC", "Titan Group - shared and consolidated", "Cross-entity records"),
]

YARDS = [("BAR", "Barnesville"), ("CAM", "Cambridge"),
         ("SHR", "Sherrodsville"), ("NPH", "New Philadelphia"),
         ("SAR", "Sardis"), ("NEW", "Newcomerstown"), ("COS", "Coshocton")]

NAMING = {
    "pattern": "YYYY-MM-DD_ENTITY_DOCTYPE_PARTY-OR-SUBJECT_IDENTIFIER_vN.ext",
    "rules": [
        "Date first, always ISO YYYY-MM-DD. The document's effective date, not "
        "the day it was scanned.",
        "Underscores separate fields. Hyphens separate words inside a field.",
        "No spaces, and none of & / \\ : * ? \" < > | # % - SharePoint "
        "rejects several of them outright.",
        "Versions are _v1, _v2. A final executed version is _EXEC.",
        "One hundred characters maximum for the filename.",
    ],
    "examples": [
        "2026-09-14_TET_INV_EOG-Resources_INV-10482_v1.pdf",
        "2026-08-31_TOL_FS_Monthly-Financial-Statements_v2.xlsx",
        "2026-07-01_TEL_LEASE_TET-Equipment-Schedule-B_EXEC.pdf",
        "2026-09-02_TGC_SOP_BMV-Fleet-Compliance_TGC-SOP-BMV-2026-01_v1.docx",
        "2026-06-15_TTI_COI_Ascent-Resources_Additional-Insured.pdf",
    ],
    "records": [
        ("Driver", "LASTNAME-FIRSTINITIAL_Hire-YYYY-MM-DD",
         "LASTNAME-FIRSTINITIAL_MVR_2026-04-02.pdf"),
        ("Unit", "UNIT-0142_2021-Peterbilt-579",
         "UNIT-0142_TITLE_2021-03-11.pdf"),
        ("Customer", "EOG-Resources", "EOG-Resources_MSA_2025-01-15_EXEC.pdf"),
        ("Vendor", "RJ-Wright-and-Sons",
         "RJ-Wright-and-Sons_W9_2026-01-08.pdf"),
        ("Well", "API-34-059-XXXXX_Hill-1",
         "API-34-059-XXXXX_MIT_2026-05-20.pdf"),
        ("Property", "New-Concord-HQ_140-S-Friendship-Dr",
         "New-Concord-HQ_DEED_2019-08-02.pdf"),
        ("Transaction", "Devco-Oil-and-Trucking", "Devco_LOI_2026-04-10_v3.pdf"),
    ],
    "codes": [
        ("AGR", "Agreement"), ("APP", "Application"), ("AUD", "Audit document"),
        ("BS", "Balance Sheet"), ("CERT", "Certificate"),
        ("COI", "Certificate of Insurance"), ("CORR", "Correspondence"),
        ("DEED", "Deed"), ("DQF", "Driver Qualification document"),
        ("DVIR", "Driver Vehicle Inspection Report"),
        ("ELD", "ELD / HOS record"), ("FS", "Financial Statement"),
        ("FT", "Field / Run Ticket"), ("INSP", "Inspection report"),
        ("INS", "Insurance policy"), ("INV", "Invoice"),
        ("LOI", "Letter of Intent"), ("MEMO", "Memorandum"),
        ("MIN", "Minutes"), ("MVR", "Motor Vehicle Record"),
        ("NDA", "Non-Disclosure Agreement"), ("PO", "Purchase Order"),
        ("POL", "Policy"), ("RES", "Resolution"), ("RPT", "Report"),
        ("SCH", "Schedule"), ("SOP", "Standard Operating Procedure"),
        ("STMT", "Statement"), ("TITLE", "Certificate of Title"),
        ("TR", "Tax Return"),
    ],
}

PRINCIPLES = [
    ("Function first, entity second",
     "Top-level folders are organised by what the business does, not by which "
     "company did it. Entity separation appears inside the functions where "
     "legal separateness is actually tested - corporate records, tax, "
     "banking, insurance, financial statements. Nine near-identical trees "
     "would be the alternative."),
    ("Numbered master folders",
     "Every master folder has a fixed File Class - 1000, 2000 and on to "
     "18000 - written five digits wide in the folder name (01000) so "
     "SharePoint sorts 2000 ahead of 10000. Numbers never change and are "
     "never reused, so the sort order is the same in every system. Inside a "
     "master folder each level adds two digits: 8000-01, then 8000-01-01."),
    ("Shallow and wide",
     "Four levels, no more. SharePoint stops at 400 characters for the whole "
     "path including the filename, and deep nesting is the single most common "
     "way a corporate file migration fails."),
    ("A template for anything that repeats",
     "Drivers, units, customers, vendors, properties, wells, employees and "
     "deals all get the same numbered shape. Copy it, rename it, and every "
     "driver file looks like every other driver file - which is what makes a "
     "DQF audit survivable."),
    ("Restricted zones are structural",
     "A folder ending in _RESTRICTED, _SEGREGATED or _PARTITIONED has its "
     "permission inheritance broken before the first document goes in. "
     "Several are legal requirements rather than preferences."),
    ("Folders for structure, metadata for retrieval",
     "Folders are the skeleton and the audit trail. Columns - Entity, Yard, "
     "Division, Customer, Unit No., Fiscal Year, Document Type, Retention "
     "Class - are how anybody actually finds anything. Do not try to encode "
     "every attribute in the folder name."),
]

WORKFLOW = [
    ("02000-01_Scan-Drop-Unfiled", "Any staff",
     "The scanner drops its output here. No naming required yet."),
    ("02000-02_In-Process-OCR", "Controller",
     "OCR applied, a searchable PDF/A created."),
    ("02000-03_Quality-Check", "Controller",
     "Legibility, page count and completeness checked against the paper."),
    ("02000-04_Ready-to-File", "Assigned staff", "Renamed to the convention."),
    ("Moved out", "Assigned staff",
     "Into its permanent home somewhere in 3000 to 17000."),
    ("02000-05_Filed-Pending-Shred", "Controller",
     "Originals held thirty days, then shredded - except the do-not-destroy "
     "list."),
    ("02000-06_Exceptions-Illegible-or-Unidentified", "Controller",
     "Rescanned, or sent back to the department it came from, weekly."),
]

RISKS = [
    ("The holdco does not exist yet",
     "3000-01-01, TEUI, is built to the v3.1 target structure, but Titan "
     "Enterprises Unlimited has not been formed. Nothing bearing a TEUI label "
     "should be filed there before the formation date - a diligence reviewer "
     "who finds TEUI documents predating formation reads the whole structure "
     "as cosmetic."),
    ("Entity separateness is tested in the files",
     "TET and TREP are owned personally as disregarded SMLLCs. If invoices, "
     "bank statements and insurance certificates sit in undifferentiated "
     "folders, the separate-entities argument weakens in a veil-piercing "
     "claim. The entity level inside 3000, 4000, 5000, 6000 and 7000 is doing "
     "real legal work."),
    ("Kimberley Transport is a third party",
     "KTL is an 80/20 partnership. Its records are partitioned and the "
     "partner's rights need confirming with counsel - what he is entitled to "
     "see, and what Titan may keep."),
    ("HR files are almost certainly commingled today",
     "I-9s, medical records, DOT physicals and workers' comp documents in one "
     "manila folder per employee is an ICE finding and an ADA exposure. "
     "Splitting them is a document-by-document job, not a bulk scan, and it "
     "is the highest-risk item in the migration."),
    ("Equipment transfer documentation gaps are already known",
     "10000-08 will start out largely empty. Filling it in retroactively, with "
     "counsel on what can be papered after the fact, is a workstream rather "
     "than a filing task."),
    ("Telematics video retention needs a written policy",
     "Video is discoverable. A vendor default with no company policy behind "
     "it is a bad position either way - too short looks like spoliation, too "
     "long builds a searchable archive of every hard brake."),
    ("Path length will bite if the plan is modified",
     "A fifth level, or staff creating free-form subfolders, produces files "
     "that sync locally and then fail to upload. Folder creation below level "
     "three belongs to the Controller and the technology contact."),
    ("The retention periods are not confirmed yet",
     "They reflect the standard federal and Ohio requirements but have not "
     "been through Titan's counsel or CPA. Nothing gets shredded on the "
     "strength of this document alone."),
]

# ---------------------------------------------------------------------------
#  Reading the index
# ---------------------------------------------------------------------------

_SUFFIX = {"_RESTRICTED": "restricted", "_SEGREGATED": "segregated",
           "_PARTITIONED": "partitioned"}


def _wall(name):
    """restricted / segregated / partitioned, or None."""
    for suffix, kind in _SUFFIX.items():
        if name.endswith(suffix):
            return kind
    return None


def _number(name):
    """The File Class, the way the CFO writes it: 01000-02_... -> 1000-02.

    The folder name pads the master number to five digits so that SharePoint,
    which sorts by text, puts 2000 before 10000. Nobody says "oh-one-thousand".
    """
    head = name.split("_", 1)[0]
    if not re.match(r"^[0-9]+(-[0-9]+)*$", head):
        return ""
    first, _, more = head.partition("-")
    return str(int(first)) + ("-" + more if more else "")


def _title(name):
    """The folder name as prose. 09000-02_Drug-and-Alcohol-Program -> the words.

    The numbers and the underscores are how the system sorts; they are not how
    anybody reads. The page shows both.

    Not every hyphen is a word separator, which is why this is not one call to
    replace(). A hyphen is kept between two numbers (396-17, 300-301) and after
    a single capital letter when the next part starts with a capital or a digit
    (W-2, K-1s, E-Verify); everywhere else it is a space - including "Phase
    I-and-II", where the I is a Roman numeral and the hyphen is just a gap.

    THE BROWSER HAS A COPY OF THIS RULE, in fileplan.html. test_fileplan.py
    runs both over every folder in the tree and compares, so the two cannot
    drift apart quietly.
    """
    body = name.split("_", 1)[1] if "_" in name else name
    for suffix in _SUFFIX:
        if body.endswith(suffix):
            body = body[:-len(suffix)]

    parts = body.split("-")
    out = parts[0]
    for prev, nxt in zip(parts, parts[1:]):
        keep = ((prev[-1:].isdigit() and nxt[:1].isdigit())
                or (len(prev) == 1 and prev.isalpha() and prev.isupper()
                    and (nxt[:1].isupper() or nxt[:1].isdigit())))
        out += ("-" if keep else " ") + nxt
    return out


def _their_title(row_title, name):
    """The index's own wording, where it says something the folder name cannot.

    A folder name cannot hold an ampersand, so the index's "Strategic M&A and
    Projects" is spelled Strategic-MandA in SharePoint. Where the index's
    title has an & or a hyphen that the name lost, the index wins. Otherwise
    the title comes from the name, so the plan and the live folders read the
    same.
    """
    t = (row_title or "").strip()
    for suffix in _SUFFIX:
        if t.endswith(suffix):
            t = t[:-len(suffix)]
    if t and ("&" in t or "-" in t) and t != _title(name):
        return t
    return None


def read_index(path=None):
    """The index's rows, blank ones skipped, in the order the CFO wrote them."""
    with open(path or INDEX, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)
                if (r.get("New Folder Path") or "").strip()]


@functools.lru_cache(maxsize=1)
def tree():
    """The structure, nested. Each node:

        name     as it appears in SharePoint
        title    the same thing, readable
        their    the index's own title, only where it beats the derived one
        num      the File Class - 1000-02
        former   the number it had before the File Class index - 00-02
        owner    the index's Primary Owner
        path     TITAN-GROUP/... - what SharePoint will see
        depth    1 for a master folder
        wall     restricted / segregated / partitioned, inherited downwards
        own      True when the wall is this folder's own, not inherited
        part     True for a record-template folder ([RECORD-ID] in the index)
        tmpl     what the template gets copied for, on the parent
        kids     children

    A template folder hangs straight off its parent here, as it did before the
    index existed. Where it sits in SharePoint - inside the parent's
    _TEMPLATE_ - is sitemap.seed's business.
    """
    root = {"name": ROOT, "title": "Titan Group", "their": None, "num": "",
            "former": "", "owner": "", "path": ROOT, "depth": 0, "wall": None,
            "own": False, "part": False, "tmpl": None, "kids": []}
    by_path = {ROOT: root}

    # Parents first, whatever order the index lists them in. It lists the
    # eighteen master folders before anything inside them.
    rows = read_index()
    rows.sort(key=lambda r: r["New Folder Path"].count("/"))
    for r in rows:
        segs = [s for s in r["New Folder Path"].strip().split("/") if s]
        if segs[0] != ROOT:
            raise ValueError("%r is not under %s" % (r["New Folder Path"], ROOT))
        part = RECORD_ID in segs
        segs = [s for s in segs if s != RECORD_ID]
        name = segs[-1]
        parent = by_path.get("/".join(segs[:-1]))
        if parent is None:
            raise ValueError("%r has no parent in the index" % r["New Folder Path"])

        wall = _wall(name)
        num = _number(name)
        node = {
            "name": name,
            "title": _title(name),
            "their": _their_title(r.get("Folder / Document Type"), name),
            "num": num,
            "former": (r.get("Former Code") or "").strip(),
            "owner": (r.get("Primary Owner") or "").strip(),
            "path": parent["path"] + "/" + name,
            "depth": parent["depth"] + 1,
            "wall": wall or parent["wall"],
            "own": bool(wall),
            "part": part or (r.get("Entry Type") or "").strip().lower()
                    == "record template",
            "tmpl": TEMPLATE_OF.get(num),
            "kids": [],
        }
        parent["kids"].append(node)
        by_path[node["path"]] = node

    def order(node):
        node["kids"].sort(key=lambda k: [int(x) for x in
                                         re.findall(r"\d+", k["num"])] or [0])
        for k in node["kids"]:
            order(k)
    order(root)
    return root


def walk(node=None):
    node = tree() if node is None else node
    yield node
    for kid in node["kids"]:
        for x in walk(kid):
            yield x


def stats():
    """Counted from the tree, not quoted from the document's prose."""
    nodes = [n for n in walk() if n["depth"] > 0]
    parts = [n for n in nodes if n["part"]]
    return {
        "folders": len(nodes),
        "masters": len([n for n in nodes if n["depth"] == 1]),
        "depth": max(n["depth"] for n in nodes),
        "walled": len([n for n in nodes if n["wall"]]),
        "own_walls": len([n for n in nodes if n["own"]]),
        "templates": len([n for n in nodes if n["tmpl"]]),
        "template_folders": len(parts),
        "longest": max(len(n["path"]) for n in nodes),
        "longest_path": max((n["path"] for n in nodes), key=len),
        "empty": len([n for n in nodes if not n["kids"]]),
    }


def _thin(node, master_owner):
    """The tree as the page wants it - short keys, nothing it will not use.

    The readable title and the full path are both left out on purpose: each is
    derivable from the name and the ancestry, and carrying them would put a
    third of this page's weight on the wire twice over. The page rebuilds them
    in two lines of JavaScript. The index's own title travels only where it
    differs, and the owner only where it is not the master folder's.
    """
    out = {"n": node["name"]}
    if node["their"]:
        out["t"] = node["their"]
    if node["former"]:
        out["f"] = node["former"]
    if node["owner"] and node["owner"] != master_owner:
        out["ow"] = node["owner"]
    if node["wall"]:
        out["w"] = node["wall"]
        if node["own"]:
            out["o"] = 1
    if node["part"]:
        out["L"] = 1
    if node["tmpl"]:
        out["tm"] = node["tmpl"]
    if node["num"] in WHY:
        out["why"] = {"who": WHY[node["num"]][0], "text": WHY[node["num"]][1]}
    if node["kids"]:
        out["k"] = [_thin(k, master_owner) for k in node["kids"]]
    return out


def _master_thin(node):
    out = _thin(node, node["owner"])
    out.pop("ow", None)
    return out


def payload():
    """Everything the page needs, in one dict."""
    masters = []
    for node in tree()["kids"]:
        num = node["num"]
        owner, about = MASTERS.get(num, ("", ""))
        letters, external = MATRIX.get(num, ("", ""))
        masters.append({
            "num": num,
            "former": node["former"],
            "name": node["name"],
            "title": node["their"] or node["title"],
            "owner": node["owner"] or owner,
            "about": about,
            "access": dict(zip(ROLES, letters.split())),
            "external": external,
            "wall": node["wall"],
        })

    return {
        "doc": DOC, "version": VERSION, "numbering": NUMBERING,
        "root": ROOT,
        "stats": stats(),
        "roles": ROLES,
        "masters": masters,
        "tree": [_master_thin(n) for n in tree()["kids"]],
        "entities": [{"code": c, "name": n, "status": s}
                     for c, n, s in ENTITIES],
        "yards": [{"code": c, "name": n} for c, n in YARDS],
        "naming": NAMING,
        "principles": [{"head": h, "text": t} for h, t in PRINCIPLES],
        "workflow": [{"folder": f, "owner": o, "what": w}
                     for f, o, w in WORKFLOW],
        "risks": [{"head": h, "text": t} for h, t in RISKS],
    }


def as_json():
    return json.dumps(payload(), ensure_ascii=False, separators=(",", ":"))


def former_names():
    """New path (below TITAN-GROUP) -> the folder's name before the index.

    Only the one-off rename of the folders already built in SharePoint needs
    this; see sitemap.renumber. It is a frozen record of the move from the old
    numbering, so it is a file of its own rather than a column in the index -
    the next draft of the index will not carry it, and should not have to.
    """
    path = os.path.join(HERE, "fileplan_renames.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


if __name__ == "__main__":
    s = stats()
    print("%(folders)s folders, %(masters)s master folders, "
          "%(depth)s levels deep" % s)
    print("%(walled)s inside a wall, %(own_walls)s of them walled off "
          "themselves" % s)
    print("longest path %(longest)s characters:" % s)
    print("  " + s["longest_path"])
    print("%s characters of JSON" % len(as_json()))
