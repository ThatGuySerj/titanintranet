"""The front-and-back layout rules, and the layout file they run from.

    python -m pytest test_duplex_layout.py -q
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import duplex_layout as dl


def sheets(order):
    """The plan as physical sheets: [(front, back), ...]."""
    return [(order[i], order[i + 1]) for i in range(0, len(order), 2)]


# ---------------------------------------------------------------------------
#  The rules
# ---------------------------------------------------------------------------

def test_a_handed_back_page_is_a_sheet_of_its_own():
    order = dl.plan("KRK")
    assert sheets(order) == [(0, None), (1, None), (2, None)]


def test_kept_pages_print_back_to_back():
    assert sheets(dl.plan("SKKK")) == [(0, 1), (2, 3)]


def test_a_new_section_never_starts_on_a_back():
    # a three-page section, then a new one: the new one gets a fresh sheet
    assert sheets(dl.plan("SKKS")) == [(0, 1), (2, None), (3, None)]


def test_a_policy_and_its_signature_page_are_separate_sheets():
    """The whole point: the signed page goes back, the policy goes home."""
    order = dl.plan("SKR")
    assert sheets(order) == [(0, 1), (2, None)]


def test_consecutive_hand_ins_each_get_a_sheet():
    assert sheets(dl.plan("RRR")) == [(0, None), (1, None), (2, None)]


def test_every_file_ends_on_a_whole_sheet():
    for codes in ("S", "SK", "SKK", "R", "KR", "SKKKK"):
        assert len(dl.plan(codes)) % 2 == 0, codes


def test_an_existing_blank_is_dropped_and_not_doubled():
    """A hand-placed blank would otherwise land where the rules put another."""
    assert sheets(dl.plan("RXR")) == [(0, None), (2, None)]


def test_every_source_page_appears_once_in_order():
    codes = "RRKKKRKKRKRRRSKSKKRS"
    order = dl.plan(codes)
    assert [i for i in order if i is not None] == list(range(len(codes)))


# ---------------------------------------------------------------------------
#  The layout file
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def layout():
    with open(os.path.join(HERE, "orientation_layout.json"), encoding="utf-8") as f:
        return json.load(f)


def test_every_code_is_one_the_rules_know(layout):
    for name, codes in layout.items():
        assert set(codes) <= dl.CODES, name


def test_the_layout_covers_every_company_folder(layout):
    folders = {k.split("/")[0] for k in layout}
    assert folders == {"Energy", "Kimberley", "Oil", "Trucking"}


def test_every_packet_opens_on_a_front(layout):
    for name, codes in layout.items():
        first = next(c for c in codes if c != "X")
        assert first in "RS", "%s starts mid-section" % name


def test_the_new_audit_form_is_a_hand_in(layout):
    """The Driver Field Audit Form swapped in on 28 September. It was page 23;
    the Ascent pages came out on 1 October (19), and the two-page DVIR policy
    went in ahead of it on 6 October (21)."""
    assert layout["Energy/SSE Packet.pdf"][20] == "R"


def test_a_file_that_has_changed_is_refused_not_guessed():
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    with pytest.raises(dl.LayoutError):
        dl.check(doc, "SKKK", "changed.pdf")          # four letters, three pages


def test_an_x_on_a_page_with_something_on_it_is_refused():
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Employee Signature: ________")
    with pytest.raises(dl.LayoutError):
        dl.check(doc, "X", "notblank.pdf")
