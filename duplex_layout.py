"""Lay an orientation packet out for front-and-back printing.

HR prints the packets double-sided, and a new hire hands some pages back and
keeps the rest. Printed straight through, those two kinds of page share sheets:
the W-4 on the back of the policy they are meant to keep, a signed
acknowledgement with the next section's first page on its reverse. Something
always goes home that should have been handed in, or the other way round.

So every page carries one of four codes, set by a person who has looked at it:

    R   handed back. Starts on a front, and its back is left blank - it is a
        sheet of its own and can be handed in without anything else attached.
    S   kept, and the first page of a new section. Starts on a front, so no
        section shares a sheet with the one before it.
    K   kept, and carries on the section it is in. Printed back to back with
        its neighbours - which is what makes double-sided printing worth it.
    X   a blank somebody already added by hand. Dropped: the layout below puts
        blanks where they are needed, and a hand-placed one would now land in
        the wrong place and waste a sheet.

The codes live in orientation_layout.json, one string per file, one letter per
page. When HR replaces a packet in SharePoint the string for that file has to
be redone - the page numbers have moved - and `check()` refuses to lay out a
file whose page count no longer matches its string rather than guessing.

Every file comes out with an even number of pages, so the packet printer's own
padding between files (orientation.merge) adds nothing, and twelve collated
copies of a set stay aligned.

    python duplex_layout.py <source folder> <output folder>
"""
import json
import os
import sys

import pymupdf

CODES = set("RSKX")


class LayoutError(ValueError):
    pass


def check(doc, codes, name=""):
    bad = set(codes) - CODES
    if bad:
        raise LayoutError("%s: unknown codes %s" % (name, "".join(sorted(bad))))
    if len(codes) != doc.page_count:
        raise LayoutError(
            "%s has %d pages but its layout string has %d letters. The file "
            "has changed since it was classified - redo its string rather "
            "than laying it out against the wrong pages."
            % (name, doc.page_count, len(codes)))
    for i, c in enumerate(codes):
        if c == "X" and not is_blank(doc[i]):
            raise LayoutError("%s page %d is marked X (an existing blank) but "
                              "it has something on it." % (name, i + 1))


def is_blank(page):
    """Nothing on it: no text, no images, no drawings, and no ink in a render.

    The render is the one that matters for scans - a scanned page has no text
    and one full-page image whether or not anything is written on it.
    """
    if page.get_text().strip():
        return False
    pm = page.get_pixmap(dpi=36, colorspace=pymupdf.csGRAY, alpha=False)
    dark = sum(1 for v in pm.samples if v < 200)
    return dark < len(pm.samples) * 0.002


def plan(codes):
    """The output order: a list of source page indexes, None for a blank."""
    out = []

    def to_front():
        if len(out) % 2:
            out.append(None)

    for i, c in enumerate(codes):
        if c == "X":
            continue
        if c == "R":
            to_front()
            out.append(i)
            out.append(None)          # nothing on the back
        elif c == "S":
            to_front()
            out.append(i)
        else:
            out.append(i)
    if len(out) % 2:
        out.append(None)              # whole sheets, so collated copies align
    return out


def build(src_path, codes, out_path):
    src = pymupdf.open(src_path)
    check(src, codes, os.path.basename(src_path))
    order = plan(codes)

    out = pymupdf.open()
    for n, i in enumerate(order):
        if i is not None:
            out.insert_pdf(src, from_page=i, to_page=i)
            continue
        # A blank the same displayed size as the page it backs, so the printer
        # never has to change paper or orientation mid-sheet.
        ref = src[order[n - 1]] if n and order[n - 1] is not None else src[0]
        out.new_page(width=ref.rect.width, height=ref.rect.height)
    out.save(out_path, garbage=4, deflate=True)
    return {"pages_in": src.page_count, "pages_out": len(order),
            "blanks": order.count(None), "sheets": len(order) // 2,
            "order": order}


def verify(src_path, codes, out_path):
    """Every rule, checked on the file actually written."""
    out = pymupdf.open(out_path)
    order = plan(codes)
    problems = []

    if out.page_count != len(order):
        problems.append("page count %d, planned %d" % (out.page_count, len(order)))
    if out.page_count % 2:
        problems.append("odd number of pages")

    kept = [i for i in order if i is not None]
    want = [i for i, c in enumerate(codes) if c != "X"]
    if kept != want:
        problems.append("source pages missing, doubled or out of order")

    for n, i in enumerate(order):
        if i is None:
            if not is_blank(out[n]):
                problems.append("output page %d should be blank" % (n + 1))
            continue
        c = codes[i]
        if c in "RS" and n % 2:
            problems.append("source page %d (%s) lands on a back" % (i + 1, c))
        if c == "R" and (n + 1 >= len(order) or order[n + 1] is not None):
            problems.append("source page %d is handed back but has something "
                            "on its reverse" % (i + 1))
    return problems


def main(src_dir, out_dir, layout_path):
    layout = json.load(open(layout_path, encoding="utf-8"))
    report = {}
    for rel, codes in sorted(layout.items()):
        src = os.path.join(src_dir, rel)
        dst = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        info = build(src, codes, dst)
        info["problems"] = verify(src, codes, dst)
        report[rel] = info
        print("%-52s %4d -> %4d pages  (+%d blank, %d sheets)  %s"
              % (rel, info["pages_in"], info["pages_out"], info["blanks"],
                 info["sheets"], "OK" if not info["problems"] else
                 "PROBLEMS: %s" % info["problems"]))
    return report


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    main(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else
         os.path.join(here, "orientation_layout.json"))
