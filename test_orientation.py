"""orientation-print-v1 tests.

No network and no SharePoint: `Library` is replaced with a fake holding a
folder tree in memory, so what is actually under test is the part that can go
wrong quietly - which names are accepted, what happens when a file has been
renamed since the popup listed it, and whether the merged PDF really contains
every page that was ticked.

The real PDFs are built here with PyMuPDF, so the merge is a genuine merge and
the page count assertion means something.

    python -m pytest test_orientation.py -q
"""
import json
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orientation


# ---------------------------------------------------------------------------
#  A folder tree, in memory
# ---------------------------------------------------------------------------

def a_pdf(pages, label="x"):
    fitz = pytest.importorskip("fitz")
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page()
        pg.insert_text((72, 72), "%s page %d" % (label, i + 1))
    out = d.tobytes()
    d.close()
    return out


class FakeLibrary:
    """Stands in for the Graph client. Records what was downloaded."""

    def __init__(self, tree):
        self.tree = tree            # {company: [(name, bytes|None, size)]}
        self.downloaded = []

    def companies(self):
        return sorted(self.tree, key=lambda s: s.lower())

    def files(self, company):
        rows = []
        for name, data, size in self.tree.get(company, []):
            low = name.lower()
            rows.append({
                "id": company + "/" + name,
                "name": name,
                "size": size,
                "mergeable": low.endswith(".pdf") or low.endswith(orientation.CONVERTIBLE),
            })
        return sorted(rows, key=lambda f: f["name"].lower())

    def pdf(self, item):
        self.downloaded.append(item["name"])
        for name, data, _ in self.tree[item["id"].split("/", 1)[0]]:
            if name == item["name"]:
                if data is None:
                    raise orientation.OrientationError("no bytes for " + name)
                return data
        raise AssertionError("asked for a file the fake does not have")


@pytest.fixture
def lib():
    return FakeLibrary({
        "Energy": [
            ("Billing Packet - Titan Energy.pdf", a_pdf(2, "billing"), 1909542),
            ("SSE Packet.pdf",                    a_pdf(3, "sse"),     3859028),
            ("Scheduling - Titan Energy.pdf",     a_pdf(1, "sched"),   68129),
            ("Notes.jpg",                         b"not-a-pdf",        1234),
        ],
        "Kimberley": [
            ("Livestock Handling.pdf", a_pdf(1, "livestock"), 500000),
        ],
        "Trucking": [],
    })


# ---------------------------------------------------------------------------
#  Listing
# ---------------------------------------------------------------------------

def test_lists_the_companies_alphabetically(lib):
    out = orientation.listing(lib)
    assert out["folders"] == ["Energy", "Kimberley", "Trucking"]


def test_no_folder_asked_for_gives_the_first(lib):
    out = orientation.listing(lib)
    assert out["folder"] == "Energy"
    assert len(out["files"]) == 4


def test_files_come_back_in_name_order_when_no_order_is_set(lib):
    # Print order is listing order, so the order this returns is the order that
    # comes out of the printer. With no configured order, alphabetical is the
    # floor - a folder nobody has sequenced yet still prints predictably.
    names = [f["name"] for f in orientation.listing(lib, "Energy")["files"]]
    assert names == sorted(names, key=str.lower)


def test_an_empty_folder_is_not_an_error(lib):
    out = orientation.listing(lib, "Trucking")
    assert out["folder"] == "Trucking"
    assert out["files"] == []


def test_non_pdf_is_listed_but_flagged(lib):
    files = {f["name"]: f for f in orientation.listing(lib, "Energy")["files"]}
    assert files["Notes.jpg"]["mergeable"] is False
    assert files["SSE Packet.pdf"]["mergeable"] is True


def test_a_docx_counts_as_mergeable(lib):
    lib.tree["Energy"].append(("Handbook.docx", a_pdf(1), 4242))
    files = {f["name"]: f for f in orientation.listing(lib, "Energy")["files"]}
    assert files["Handbook.docx"]["mergeable"] is True


def test_unknown_folder_says_what_there_is(lib):
    with pytest.raises(orientation.OrientationError) as e:
        orientation.listing(lib, "Nope")
    assert "Energy" in str(e.value)


# ---------------------------------------------------------------------------
#  Names the page never sends
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "../../../etc/passwd",
    "HR/Orientation Forms/Energy/x.pdf",
    "..",
    ".hidden",
    "sub\\dir.pdf",
    "nul\x00.pdf",
])
def test_paths_are_refused_not_normalised(lib, bad):
    # The page sends bare names. Anything shaped like a path came from
    # somewhere else, and the answer is no rather than an attempt to clean it.
    with pytest.raises(orientation.OrientationError):
        orientation.build(lib, "Energy", [bad])
    with pytest.raises(orientation.OrientationError):
        orientation.listing(lib, bad)


def test_a_name_the_folder_does_not_have_is_an_error(lib):
    # Renamed in SharePoint between the popup listing it and Print being
    # pressed. Nine ticked must not print as eight.
    with pytest.raises(orientation.OrientationError) as e:
        orientation.build(lib, "Energy",
                          ["SSE Packet.pdf", "Gone Away.pdf"])
    assert "Gone Away.pdf" in str(e.value)


def test_nothing_selected_is_an_error(lib):
    with pytest.raises(orientation.OrientationError):
        orientation.build(lib, "Energy", [])


def test_a_non_mergeable_pick_is_refused_before_downloading(lib):
    with pytest.raises(orientation.OrientationError) as e:
        orientation.build(lib, "Energy", ["Notes.jpg"])
    assert "Notes.jpg" in str(e.value)
    assert lib.downloaded == []


# ---------------------------------------------------------------------------
#  The merge
# ---------------------------------------------------------------------------

def test_merged_pdf_has_every_page_of_every_pick(lib):
    # duplex off, so this counts the real pages and not the blanks the
    # front-and-back padding adds. The padding has its own tests below.
    fitz = pytest.importorskip("fitz")
    out = orientation.build(lib, "Energy",
                            ["Billing Packet - Titan Energy.pdf",   # 2
                             "SSE Packet.pdf",                      # 3
                             "Scheduling - Titan Energy.pdf"],      # 1
                            duplex=False)
    d = fitz.open(stream=out, filetype="pdf")
    assert d.page_count == 6
    d.close()


def test_merge_keeps_the_order_it_was_given(lib):
    fitz = pytest.importorskip("fitz")
    out = orientation.build(lib, "Energy",
                            ["SSE Packet.pdf",
                             "Billing Packet - Titan Energy.pdf"])
    d = fitz.open(stream=out, filetype="pdf")
    first = d[0].get_text()
    d.close()
    assert "sse" in first


def test_copies_goes_in_the_viewer_preferences_not_the_pages(lib):
    fitz = pytest.importorskip("fitz")
    out = orientation.build(lib, "Energy", ["SSE Packet.pdf"], copies=12,
                            duplex=False)
    d = fitz.open(stream=out, filetype="pdf")
    # 3 pages, not 36. Repeating the pages for twelve new hires would turn a
    # 37 MB set into 450 MB.
    assert d.page_count == 3
    d.close()
    assert b"NumCopies" in out


def test_one_copy_needs_no_viewer_preference(lib):
    out = orientation.build(lib, "Energy", ["SSE Packet.pdf"], copies=1)
    assert b"NumCopies" not in out


def test_copies_is_clamped(lib):
    fitz = pytest.importorskip("fitz")
    for n in (0, -5, 9999, None):
        out = orientation.build(lib, "Energy", ["SSE Packet.pdf"], copies=n,
                                duplex=False)
        d = fitz.open(stream=out, filetype="pdf")
        assert d.page_count == 3
        d.close()


# ---------------------------------------------------------------------------
#  Front and back
# ---------------------------------------------------------------------------
# These are printed duplex. A packet with an odd page count would otherwise
# leave the next packet's first page on the back of its last sheet.

def pages_of(pdf):
    fitz = pytest.importorskip("fitz")
    d = fitz.open(stream=pdf, filetype="pdf")
    n = d.page_count
    d.close()
    return n


def starts_of(pdf):
    """1-based page number each packet starts on, read off the page text."""
    fitz = pytest.importorskip("fitz")
    d = fitz.open(stream=pdf, filetype="pdf")
    out, seen = [], None
    for i in range(d.page_count):
        txt = d[i].get_text().strip()
        label = txt.split(" page")[0] if txt else ""
        if label and label != seen:
            out.append(i + 1)
            seen = label
    d.close()
    return out


def test_every_packet_starts_on_a_front_side(lib):
    # billing 2, sse 3, scheduling 1 -> without padding sse starts on 3 (fine)
    # but scheduling would start on 6, the BACK of sheet 3.
    out = orientation.build(lib, "Energy",
                            ["Billing Packet - Titan Energy.pdf",
                             "SSE Packet.pdf",
                             "Scheduling - Titan Energy.pdf"], duplex=True)
    starts = starts_of(out)
    assert all(p % 2 == 1 for p in starts), \
        "a packet starting on an even page is on the back of a sheet: %s" % starts


def test_odd_packets_get_one_blank_each(lib):
    info = {}
    orientation.build(lib, "Energy",
                      ["Billing Packet - Titan Energy.pdf",   # 2, even
                       "SSE Packet.pdf",                      # 3, odd  -> +1
                       "Scheduling - Titan Energy.pdf"],      # 1, odd  -> +1
                      duplex=True, info=info)
    assert info["blanks"] == 2
    assert info["pages"] == 8      # 2 + (3+1) + (1+1)


def test_the_whole_set_ends_even_so_collated_copies_stay_aligned(lib):
    # The one that only shows up when somebody prints twelve: an odd total
    # puts copy 2 on the back of copy 1's last sheet.
    out = orientation.build(lib, "Energy", ["SSE Packet.pdf"],
                            copies=12, duplex=True)
    assert pages_of(out) % 2 == 0


def test_duplex_off_adds_nothing(lib):
    info = {}
    out = orientation.build(lib, "Energy",
                            ["Billing Packet - Titan Energy.pdf",
                             "SSE Packet.pdf",
                             "Scheduling - Titan Energy.pdf"],
                            duplex=False, info=info)
    assert info["blanks"] == 0
    assert pages_of(out) == 6


def test_duplex_is_the_default(lib):
    info = {}
    orientation.build(lib, "Energy", ["SSE Packet.pdf"], info=info)
    assert info["blanks"] == 1


def test_a_blank_matches_the_sheet_it_backs_onto(lib):
    # A landscape packet must not get a portrait blank, or the printer either
    # scales the stack or refuses it.
    fitz = pytest.importorskip("fitz")
    d = fitz.open()
    pg = d.new_page(width=792, height=612)      # landscape Letter
    pg.insert_text((72, 72), "wide page 1")
    lib.tree["Energy"].append(("Wide.pdf", d.tobytes(), 1000))
    d.close()

    out = orientation.build(lib, "Energy", ["Wide.pdf"], duplex=True)
    d = fitz.open(stream=out, filetype="pdf")
    assert d.page_count == 2
    assert round(d[1].rect.width) == 792 and round(d[1].rect.height) == 612
    d.close()


def test_the_blank_is_actually_blank(lib):
    fitz = pytest.importorskip("fitz")
    out = orientation.build(lib, "Energy", ["SSE Packet.pdf"], duplex=True)
    d = fitz.open(stream=out, filetype="pdf")
    assert d[3].get_text().strip() == ""
    d.close()


def test_info_is_optional(lib):
    # app.py passes a dict, the tests above pass a dict, and nothing should
    # break for a caller that does not care.
    assert orientation.build(lib, "Energy", ["SSE Packet.pdf"])


def test_a_corrupt_file_says_which_one(lib):
    lib.tree["Energy"].append(("Broken.pdf", b"%PDF-1.4 truncated", 18))
    with pytest.raises(orientation.OrientationError) as e:
        orientation.build(lib, "Energy", ["SSE Packet.pdf", "Broken.pdf"])
    assert "2 of 2" in str(e.value)


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

def test_from_env_names_what_is_missing(monkeypatch):
    for k in ("TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(orientation.NotConfigured) as e:
        orientation.from_env()
    assert "TENANT_ID" in str(e.value)


def test_from_env_defaults_to_the_company_documents_site(monkeypatch):
    monkeypatch.setenv("TENANT_ID", "t")
    monkeypatch.setenv("GRAPH_CLIENT_ID", "c")
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "s")
    for k in ("SP_HOST", "SP_SITE_PATH", "SP_LIBRARY", "ORIENTATION_ROOT",
              "SP_DRIVE_ID"):
        monkeypatch.delenv(k, raising=False)
    lib = orientation.from_env()
    assert lib.site_path == "sites/CompanyDocuments"
    assert lib.library == "All Company Documents"
    assert lib.root == "HR/Orientation Forms"


def test_not_configured_is_an_orientation_error(monkeypatch):
    # The routes catch NotConfigured for a 501 and OrientationError for a 502.
    # If the class hierarchy changes, an unconfigured server starts answering
    # 500 and reads like a crash.
    assert issubclass(orientation.NotConfigured, orientation.OrientationError)


# ---------------------------------------------------------------------------
#  Print order
# ---------------------------------------------------------------------------
#
# Alphabetical was never the order orientation happens in. The sequence below
# is the one HR walks a new hire through, and it is in site/config.json rather
# than in the code so HR can change it.

ENERGY = [
    "ADP Packet.pdf",
    "Billing Packet - Titan Energy.pdf",
    "Contacts.pdf",
    "Holiday Pay Packet - Titan Energy.pdf",
    "Insurance Folder - Left Side.pdf",
    "Insurance Folder - Right Side.pdf",
    "Light Duty Packet - Titan Energy.pdf",
    "Principal Booklet - Weekly.pdf",
    "Safe Driving Packet.pdf",
    "Scheduling - Titan Energy.pdf",
    "SSE Packet.pdf",
]

WANTED = [
    "Contacts.pdf",
    "ADP Packet.pdf",
    "Holiday Pay Packet - Titan Energy.pdf",
    "Insurance Folder - Left Side.pdf",
    "Insurance Folder - Right Side.pdf",
    "Principal Booklet - Weekly.pdf",
    "Billing Packet - Titan Energy.pdf",
    "Scheduling - Titan Energy.pdf",
    "Light Duty Packet - Titan Energy.pdf",
    "SSE Packet.pdf",
    "Safe Driving Packet.pdf",
]


@pytest.fixture(scope="module")
def energy_order():
    """The real one, off disk. A test against a list typed out here would pass
    while the site printed something else."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "site", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg["orientation"]["order"]["Energy"]


def files(names):
    return [{"name": n} for n in names]


def test_the_energy_packets_come_out_in_the_order_hr_asked_for(energy_order):
    """The whole point. Contacts and ADP first, Safe Driving last, and the
    insurance folder's left side before its right - which alphabetically it
    already is, by luck rather than design."""
    got = [f["name"] for f in orientation.in_order(files(ENERGY), energy_order)]
    assert got == WANTED


def test_the_order_covers_every_packet_in_the_folder(energy_order):
    """Anything unnamed falls to the end. That is the right failure - it still
    prints - but for the folder as it stands today nothing should be landing
    there by accident."""
    import re
    pats = [re.compile(r"\b%s\b" % re.escape(k), re.I) for k in energy_order]
    for name in ENERGY:
        assert any(p.search(name) for p in pats), name


def test_no_two_entries_claim_the_same_packet(energy_order):
    """Two keys matching one file means one of them is doing nothing, and the
    packet it was meant to place is somewhere else entirely."""
    import re
    for name in ENERGY:
        hits = [k for k in energy_order
                if re.search(r"\b%s\b" % re.escape(k), name, re.I)]
        assert len(hits) == 1, (name, hits)


def test_a_packet_nobody_sequenced_prints_last_rather_than_vanishing(energy_order):
    got = [f["name"] for f in
           orientation.in_order(files(ENERGY + ["Brand New Packet.pdf"]),
                                energy_order)]
    assert got[-1] == "Brand New Packet.pdf"
    assert got[:-1] == WANTED


def test_a_renamed_packet_keeps_its_place(energy_order):
    """Matching is on words inside the name, so a year or a tidy-up does not
    silently drop a packet to the bottom of the pile."""
    renamed = [n.replace("Insurance Folder - Left Side.pdf",
                         "Insurance Folder - Left Side 2026.pdf")
               for n in ENERGY]
    got = [f["name"] for f in orientation.in_order(files(renamed), energy_order)]
    assert got[3] == "Insurance Folder - Left Side 2026.pdf"


def test_sse_does_not_match_assessment(energy_order):
    """Whole words, not substrings. A substring match would have put a drug
    assessment in the SSE packet's place and nobody would have looked."""
    got = [f["name"] for f in
           orientation.in_order(files(["Drug Assessment.pdf", "SSE Packet.pdf"]),
                                energy_order)]
    assert got == ["SSE Packet.pdf", "Drug Assessment.pdf"]


def test_no_order_leaves_it_alphabetical():
    got = [f["name"] for f in orientation.in_order(files(ENERGY), None)]
    assert got == sorted(ENERGY, key=str.lower)


def test_the_merge_reorders_what_the_page_sent(energy_order):
    """A tab left open since before the order was set would post the names in
    the old sequence. The pile it produces has to be right anyway."""
    lib = FakeLibrary({"Energy": [(n, a_pdf(1, n), 1000) for n in ENERGY]})
    orientation.build(lib, "Energy", list(reversed(ENERGY)),
                      order=energy_order)
    assert lib.downloaded == WANTED


def test_the_merge_keeps_the_order_for_a_partial_pick(energy_order):
    lib = FakeLibrary({"Energy": [(n, a_pdf(1, n), 1000) for n in ENERGY]})
    picked = ["Safe Driving Packet.pdf", "Contacts.pdf",
              "Insurance Folder - Right Side.pdf"]
    orientation.build(lib, "Energy", picked, order=energy_order)
    assert lib.downloaded == ["Contacts.pdf",
                              "Insurance Folder - Right Side.pdf",
                              "Safe Driving Packet.pdf"]


def test_the_routes_hand_the_configured_order_to_both_of_them():
    """The listing and the merge have to read the same list. If only the
    listing did, the page would show one order and print another."""
    pytest.importorskip("flask")
    pytest.importorskip("psycopg")
    import app as appmod

    order = appmod._packet_order("Energy")
    assert order and order[0] == "Contacts"
    assert appmod._packet_order("Kimberley") == []
    assert appmod._packet_order("") == []
