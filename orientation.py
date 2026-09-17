"""Batch printing the orientation packets out of SharePoint.

One person runs orientation. They used to open nine PDFs out of a SharePoint
folder and print each one, then do it again for the next new hire. This reads
the folder, merges the chosen files into a single PDF, and hands that back so
the browser opens one print dialog.

Why the merge has to happen here and not in the page: a browser cannot print a
cross-origin PDF programmatically, SharePoint refuses to be put in an iframe,
and JavaScript cannot even fetch the files - SharePoint sends no CORS headers
for another origin. Nine popup tabs get blocked as well. So the server does it.

Reading SharePoint uses the same Entra app registration as the mail ingestion
in graph.py, with one more application permission. Sites.Selected is the one to
ask IT for, granted read on the Company Documents site only; Sites.Read.All
also works and is far broader than this needs.

Merging uses PyMuPDF, which is already a dependency for the ticket OCR, so this
adds no new package.

    Company Documents/                         SP_SITE_PATH
      All Company Documents/                   SP_LIBRARY
        HR/Orientation Forms/                  ORIENTATION_ROOT
          Energy/                              a company, becomes a dropdown
            Billing Packet - Titan Energy.pdf  a tick box
          Kimberley/

Adding a company is making a folder. Nothing here lists packet names.

stdlib plus fitz. Graph endpoints involved:

    POST /{tenant}/oauth2/v2.0/token
    GET  /sites/{host}:/{sitePath}
    GET  /sites/{siteId}/drives
    GET  /drives/{driveId}/root:/{path}:/children
    GET  /drives/{driveId}/items/{itemId}/content[?format=pdf]
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

AUTHORITY = "https://login.microsoftonline.com"
GRAPH = "https://graph.microsoft.com/v1.0"

# Anything Graph will render to PDF for us. A file whose type is not here is
# listed but cannot be merged, and the page says so rather than the print
# silently missing a page.
CONVERTIBLE = (".doc", ".docx", ".rtf", ".odt", ".txt",
               ".ppt", ".pptx", ".odp",
               ".xls", ".xlsx", ".ods")


class OrientationError(RuntimeError):
    """Something the person at the browser needs told about."""


class NotConfigured(OrientationError):
    """The environment has not been set up for this yet."""


# ---------------------------------------------------------------------------
#  Graph
# ---------------------------------------------------------------------------

class Library:
    """One SharePoint document library, read-only."""

    def __init__(self, tenant, client_id, client_secret,
                 host, site_path, library, root, drive_id=None):
        self.tenant = tenant
        self.client_id = client_id
        self.client_secret = client_secret
        self.host = host
        self.site_path = site_path.strip("/")
        self.library = library
        self.root = root.strip("/")
        self._drive_id = drive_id or None
        self._token = None
        self._token_expires = 0

    # -- auth --------------------------------------------------------------
    def token(self):
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        body = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode()
        url = "%s/%s/oauth2/v2.0/token" % (AUTHORITY, self.tenant)
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise OrientationError(
                "Could not get a Microsoft token (%s). Check TENANT_ID, "
                "GRAPH_CLIENT_ID and GRAPH_CLIENT_SECRET. %s" % (e.code, detail))
        self._token = out["access_token"]
        self._token_expires = time.time() + int(out.get("expires_in", 3600))
        return self._token

    def _json(self, path):
        url = path if path.startswith("http") else GRAPH + path
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + self.token())
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code == 403:
                raise OrientationError(
                    "Microsoft refused access to the document library (403). "
                    "The app registration needs Sites.Selected with read on "
                    "the Company Documents site, and admin consent. %s" % detail)
            if e.code == 404:
                raise OrientationError(
                    "Not found in SharePoint: %s. %s" % (url, detail))
            raise OrientationError("Graph %s: %s %s" % (url, e.code, detail))

    def _bytes(self, url):
        # A 302 to a pre-authenticated storage URL is the normal answer to a
        # /content request. That second request must NOT carry the bearer
        # token - the storage host rejects a request that has both its own
        # signature and an Authorization header - and urllib keeps headers we
        # set across a redirect. So the redirect is caught and re-issued clean.
        #
        # This uses its OWN opener rather than install_opener(), which would
        # swap the default opener out from under graph.py and everything else
        # in the process.
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + self.token())
        try:
            with _OPENER.open(req, timeout=300) as r:
                return r.read()
        except _Redirected as move:
            with urllib.request.urlopen(move.url, timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise OrientationError("Could not download from SharePoint (%s). %s"
                                   % (e.code, detail))

    # -- the library -------------------------------------------------------
    def drive_id(self):
        """The library's drive id, looked up by its display name."""
        if self._drive_id:
            return self._drive_id
        site = self._json("/sites/%s:/%s" % (self.host, self.site_path))
        drives = self._json("/sites/%s/drives" % site["id"])
        want = self.library.strip().lower()
        found = []
        for d in drives.get("value", []):
            name = (d.get("name") or "")
            found.append(name)
            if name.strip().lower() == want:
                self._drive_id = d["id"]
                return self._drive_id
        raise OrientationError(
            "No document library called %r on that site. Libraries found: %s. "
            "Set SP_LIBRARY to one of those." % (self.library, ", ".join(found)))

    def _children(self, path):
        path = path.strip("/")
        if path:
            url = ("/drives/%s/root:/%s:/children"
                   % (self.drive_id(), urllib.parse.quote(path)))
        else:
            url = "/drives/%s/root/children" % self.drive_id()
        out = self._json(url + "?$top=200&$select=id,name,size,folder,file")
        rows = list(out.get("value", []))
        nxt = out.get("@odata.nextLink")
        pages = 0
        while nxt and pages < 10:
            out = self._json(nxt)
            rows.extend(out.get("value", []))
            nxt = out.get("@odata.nextLink")
            pages += 1
        return rows

    def companies(self):
        """The sub-folders of the orientation root, alphabetically."""
        rows = self._children(self.root)
        return sorted((r["name"] for r in rows if r.get("folder")),
                      key=lambda s: s.lower())

    def files(self, company):
        """The files in one company's folder: id, name, size, mergeable."""
        path = self.root + ("/" + company if company else "")
        out = []
        for r in self._children(path):
            if r.get("folder"):
                continue
            name = r["name"]
            low = name.lower()
            out.append({
                "id": r["id"],
                "name": name,
                "size": r.get("size") or 0,
                "mergeable": low.endswith(".pdf") or low.endswith(CONVERTIBLE),
            })
        return sorted(out, key=lambda f: f["name"].lower())

    def pdf(self, item):
        """One file as PDF bytes, converting if it is not one already."""
        base = "%s/drives/%s/items/%s/content" % (GRAPH, self.drive_id(), item["id"])
        if item["name"].lower().endswith(".pdf"):
            return self._bytes(base)
        return self._bytes(base + "?format=pdf")


class _Redirected(Exception):
    """A 3xx, surfaced so the next hop can be made without our headers."""

    def __init__(self, url):
        self.url = url


class _StopRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(newurl)


# Private to this module. Nothing else in the process is affected.
_OPENER = urllib.request.build_opener(_StopRedirects)


# ---------------------------------------------------------------------------
#  Merging
# ---------------------------------------------------------------------------

def merge(pdfs, copies=1, duplex=True, info=None):
    """Several PDFs into one, in the order given.

    `copies` is written into the PDF's viewer preferences rather than by
    repeating the pages. A full Energy set is about 37 MB; twelve sets of
    repeated pages would be some 450 MB, slow to build and enough to choke a
    print spooler. Acrobat reads /NumCopies and fills the dialog in; browser
    viewers ignore it, which is why the page also tells the person the number
    to type. Either way the printer does the collating, which is what printers
    are good at.

    `duplex` pads every packet to an even number of pages, so each one starts
    on a fresh sheet. These get printed front and back: without the padding, a
    packet with an odd page count leaves the next packet's first page on the
    back of its last sheet, and the new hire is handed a Safe Driving Packet
    with the back of the Holiday Pay form on the reverse of page 3.

    The padding runs after the LAST packet too, not just between them. If it
    did not, an odd total would put the second collated copy on the back of the
    first copy's last sheet - the same fault, one level up, and only visible
    once somebody prints twelve.
    """
    import fitz          # PyMuPDF, already required for the ticket OCR

    if not pdfs:
        raise OrientationError("Nothing was selected to print.")

    blanks = 0
    out = fitz.open()
    try:
        for i, data in enumerate(pdfs):
            try:
                src = fitz.open(stream=data, filetype="pdf")
            except Exception as e:
                raise OrientationError(
                    "File %d of %d could not be read as a PDF (%s). Open it in "
                    "SharePoint to check it is not corrupt." % (i + 1, len(pdfs), e))
            try:
                out.insert_pdf(src)
            finally:
                src.close()

            if duplex and out.page_count % 2:
                # Match the sheet it backs onto rather than assuming Letter -
                # a landscape or legal packet would otherwise get a portrait
                # blank and the printer would either scale the stack or refuse.
                last = out[out.page_count - 1].rect
                out.new_page(width=last.width, height=last.height)
                blanks += 1

        if out.page_count == 0:
            raise OrientationError("The merged file came out with no pages in it.")

        # Reported back so the page can say the blanks were deliberate. A
        # blank sheet in the middle of a stack reads as a misprint, and the
        # cure for that is a sentence, not a different PDF.
        if info is not None:
            info["pages"] = out.page_count
            info["blanks"] = blanks
            info["files"] = len(pdfs)

        n = max(1, min(int(copies or 1), 50))
        if n > 1:
            try:
                out.xref_set_key(out.pdf_catalog(), "ViewerPreferences",
                                 "<</NumCopies %d>>" % n)
            except Exception:
                # A copy count the viewer fills in is a convenience, not the
                # feature. If this PyMuPDF cannot set it, still return the PDF.
                pass

        return out.tobytes(garbage=3, deflate=True)
    finally:
        out.close()


# ---------------------------------------------------------------------------
#  What the routes call
# ---------------------------------------------------------------------------

def _clean_segment(s):
    """A folder or file name, or nothing.

    The page sends names, never paths. Anything with a separator or a parent
    reference in it did not come from the page, so it is refused outright
    rather than normalised into something that might escape the folder.
    """
    s = (s or "").strip()
    if not s:
        return ""
    if "/" in s or "\\" in s or s.startswith(".") or ".." in s or "\x00" in s:
        raise OrientationError("That is not a name this can look up: %r" % s[:80])
    return s


def from_env():
    missing = [k for k in ("TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET")
               if not (os.environ.get(k) or "").strip()]
    if missing:
        raise NotConfigured(
            "Packet printing needs %s in the environment - the same Entra app "
            "registration the mail ingestion uses, plus Sites.Selected read on "
            "the Company Documents site." % ", ".join(missing))
    host = (os.environ.get("SP_HOST") or "netorgft9778845.sharepoint.com").strip()
    return Library(
        tenant=os.environ["TENANT_ID"].strip(),
        client_id=os.environ["GRAPH_CLIENT_ID"].strip(),
        client_secret=os.environ["GRAPH_CLIENT_SECRET"].strip(),
        host=host,
        site_path=(os.environ.get("SP_SITE_PATH") or "sites/CompanyDocuments").strip(),
        library=(os.environ.get("SP_LIBRARY") or "All Company Documents").strip(),
        root=(os.environ.get("ORIENTATION_ROOT") or "HR/Orientation Forms").strip(),
        drive_id=(os.environ.get("SP_DRIVE_ID") or "").strip() or None,
    )


def in_order(files, order):
    """The folder's files in the order they are meant to be handed over.

    Alphabetical is not the order anybody orientates in. Energy starts with
    Contacts and ADP and ends with the Safe Driving packet, and the middle is
    the sequence HR walks a new hire through - the insurance folder's left side
    before its right side, which alphabetically is the wrong way round only by
    luck.

    Matching is on whole words inside the filename, case-insensitively, rather
    than on the filename itself: "Insurance Folder - Left Side.pdf" gaining a
    year or losing a hyphen should not silently drop it to the bottom of the
    pile. Whole words and not substrings because "SSE" would otherwise match a
    future "Drug Assessment.pdf".

    Anything the order does not mention goes last, alphabetically. A packet
    added to SharePoint this morning therefore still prints - at the end, where
    it is noticed - rather than disappearing because nobody updated a list.
    """
    keys = [k.strip() for k in (order or []) if str(k).strip()]
    pats = [re.compile(r"\b%s\b" % re.escape(k), re.I) for k in keys]

    def rank(f):
        name = f["name"] if isinstance(f, dict) else str(f)
        for i, pat in enumerate(pats):
            if pat.search(name):
                return (i, name.lower())
        return (len(pats), name.lower())

    return sorted(files, key=rank)


def listing(lib, company="", order=None):
    """What GET /api/orientation answers with."""
    company = _clean_segment(company)
    companies = lib.companies()
    if company and company not in companies:
        raise OrientationError(
            "There is no %r folder in the orientation forms. There is: %s."
            % (company, ", ".join(companies) or "nothing yet"))
    if not company:
        company = companies[0] if companies else ""
    files = in_order(lib.files(company), order) if company else []
    return {
        "folders": companies,
        "folder": company,
        "files": [{"name": f["name"], "size": f["size"],
                   "mergeable": f["mergeable"]} for f in files],
    }


def build(lib, company, names, copies=1, duplex=True, info=None, order=None):
    """What POST /api/print-packets answers with: one PDF, as bytes.

    Every name is checked against what the folder actually holds, rather than
    trusted and passed to Graph. A name the folder does not have is an error,
    not an empty page - if HR ticks nine things they should get nine things or
    be told which one is missing.

    The order is applied here as well as in the listing. The page sends the
    names in the order it drew them, so the two normally agree - but the print
    order is a property of the packet and not of a browser tab that might have
    been open since before the order was set, and getting it wrong means a
    stapled pile in the wrong sequence rather than an error anybody sees.
    """
    company = _clean_segment(company)
    wanted = [_clean_segment(n) for n in (names or []) if _clean_segment(n)]
    if not wanted:
        raise OrientationError("Nothing was selected to print.")

    have = {f["name"]: f for f in lib.files(company)}
    missing = [n for n in wanted if n not in have]
    if missing:
        raise OrientationError(
            "Not in that folder any more: %s. Close the popup and open it "
            "again to re-read the folder." % ", ".join(missing[:5]))

    cannot = [n for n in wanted if not have[n]["mergeable"]]
    if cannot:
        raise OrientationError(
            "Cannot be turned into PDF pages: %s. Save a PDF copy into the "
            "folder and print that instead." % ", ".join(cannot[:5]))

    # Only when there is an order to apply. With none configured the caller's
    # order is the order - that is what the page's tick boxes mean, and
    # re-sorting it alphabetically here would quietly override a folder nobody
    # has sequenced yet.
    if order:
        wanted = [f["name"] for f in in_order([have[n] for n in wanted], order)]
    return merge([lib.pdf(have[n]) for n in wanted], copies, duplex, info)
