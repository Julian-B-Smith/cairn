"""Standing tests for the interpretation queue (D77).

Cairn's other checks ask "is this citation real and located?". These ask "which
reading did we mean?" — and never answer it: detection is deterministic, the proposal
is labelled a recommendation, and the resolution is a human judgment.
"""

from __future__ import annotations

import pytest

from cairn.ambiguity import (
    NUMERAL_SENSE,
    collect,
    excluded_numerals,
    numeral_sense,
)
from cairn.patents import numeral_mentions

pytestmark = pytest.mark.layer0

TEXT = (
    "DESCRIPTION\n"
    "A ceramic scrubber 20 is provided downstream of the reactor.\n"
    "The upper chamber 80 has a maximum diameter of 20 inches.\n"
    "\nWhat is claimed is:\n\n1. A system.\n"
)


def test_a_token_that_is_both_a_part_and_a_measurement_is_surfaced():
    """The case that produced a visibly wrong highlight: reference numeral 20 is a
    ceramic scrubber, and "a maximum diameter of 20 inches" is a dimension. Same three
    glyphs, different facts — and the code used to pick one silently."""
    ambs = numeral_sense(TEXT, numeral_mentions(TEXT))
    a = next(x for x in ambs if x.label == "20")
    assert a.kind == NUMERAL_SENSE
    assert "scrubber" in a.where["recited_as"]
    assert "inches" in a.where["quantity_as"]
    assert {o.value for o in a.options} == {"both", "part only", "measurement only"}


def test_the_proposal_is_a_recommendation_and_never_a_default():
    """Nothing is applied until a human chooses. A recommendation that quietly acts is
    the machine deciding, which is the whole thing this panel exists to stop."""
    a = next(x for x in numeral_sense(TEXT, numeral_mentions(TEXT)) if x.label == "20")
    assert a.proposed == "both"
    # …and the proposal is one of the offered readings, never a fourth thing.
    assert a.proposed in {o.value for o in a.options}


def test_a_number_used_only_as_a_measurement_raises_no_question():
    """No recitation, no fork: a bare quantity was never a candidate reference numeral,
    so surfacing it would be noise in a queue whose value is that it is short."""
    text = ("DESCRIPTION\nThe flow is 45 gallons per minute.\n"
            "\nWhat is claimed is:\n\n1. A system.\n")
    assert numeral_sense(text, numeral_mentions(text)) == []


def test_a_resolved_ambiguity_leaves_the_queue_but_can_still_be_read_back():
    ambs = collect(text=TEXT, mentions=numeral_mentions(TEXT))
    assert any(a.amb_id == f"{NUMERAL_SENSE}:20" for a in ambs)
    left = collect(text=TEXT, mentions=numeral_mentions(TEXT),
                   resolved={f"{NUMERAL_SENSE}:20"})
    assert all(a.amb_id != f"{NUMERAL_SENSE}:20" for a in left)


def test_ruling_a_token_a_measurement_feeds_back_and_stops_it_being_lit():
    """A ruling that changes nothing downstream is a ruling the reviewer stops making.
    "20 is never a part here" must remove it from what the figure overlay offers."""
    assert excluded_numerals({f"{NUMERAL_SENSE}:20": "measurement only"}) == {"20"}
    assert excluded_numerals({f"{NUMERAL_SENSE}:20": "both"}) == set()


def test_only_ambiguity_rulings_are_read_back_as_readings(tmp_path):
    """One log, several target kinds. A consumer that reads another kind's records acts
    on an assertion nobody made — the guard that also keeps a figure ruling from
    injecting a numeral onto a sheet."""
    from cairn.adjudication import Adjudication, AdjudicationLog
    from cairn.ambiguity import TARGET_KIND, resolutions

    log = AdjudicationLog(tmp_path / "adj.jsonl")
    log.append(Adjudication(
        adj_id=f"{NUMERAL_SENSE}:20::correct::2026-08-15", kind="correct",
        target_kind=TARGET_KIND, target={"amb_id": f"{NUMERAL_SENSE}:20"},
        value={"reading": "measurement only"}, by="J. Smith", on="2026-08-15"))
    log.append(Adjudication(                       # a marks-on-sheets ruling, not a reading
        adj_id="drawn_not_recited:99::refute::2026-08-15", kind="refute",
        target_kind="figure-numeral", target={"page": 2, "numeral": "99"},
        by="J. Smith", on="2026-08-15"))

    got = resolutions(log)
    assert got == {f"{NUMERAL_SENSE}:20": "measurement only"}


def test_a_figure_ruling_never_injects_a_numeral_onto_the_sheet(tmp_path):
    """The guard the shared log made necessary: confirming "FIG. 6 is on sheet p.7"
    must not add a mark called "6" to that sheet."""
    from cairn.adjudication import Adjudication, AdjudicationLog
    from cairn.ambiguity import FIGURE_GUESS, TARGET_KIND
    from cairn.figures_map import apply_adjudications

    log = AdjudicationLog(tmp_path / "adjudications.jsonl")
    log.append(Adjudication(
        adj_id=f"{FIGURE_GUESS}:6::confirm::2026-08-15", kind="confirm",
        target_kind=TARGET_KIND, target={"amb_id": f"{FIGURE_GUESS}:6", "fig": "6",
                                         "page": 7},
        value={"reading": "yes"}, by="J. Smith", on="2026-08-15"))
    man = {"pages": [{"page": 7, "numerals": []}]}
    assert apply_adjudications(man, tmp_path)["pages"][0]["numerals"] == []


class _Cov:
    def __init__(self, misreads):
        self.likely_misreads = misreads


def test_an_unresolved_ocr_conflict_names_both_readings(tmp_path):
    """The record's fields are `read_as` / `actually`. Reading keys that do not exist
    rendered every one of these as “Is this mark “?” or “the recited form”?” — two
    fallback defaults where the two candidate readings belonged, which is unreadable
    and looks like a substitution bug because it is one."""
    from cairn.ambiguity import OCR_CONFLICT, ocr_conflict

    cov = _Cov([{"read_as": "12", "actually": "72", "page": 6, "unresolved": True,
                 "bbox": [0.4, 0.3, 0.02, 0.015],
                 "message": "engines disagree on one mark"}])
    a = ocr_conflict(cov)[0]
    assert a.kind == OCR_CONFLICT
    assert a.label == "12 / 72"
    assert "“12” or “72”" in a.question
    assert {o.value for o in a.options} == {"12", "72", "neither"}
    assert a.where["bbox"] == [0.4, 0.3, 0.02, 0.015]     # so the sheet can be shown


def test_an_unresolved_conflict_carries_no_recommendation():
    """The one kind that must not propose. "Unresolved" means the specification ties
    NEITHER reading to that figure — so the signals a recommendation would come from
    are exactly the ones missing, and offering a favourite would manufacture confidence
    in the single case defined by its absence."""
    from cairn.ambiguity import ocr_conflict

    cov = _Cov([{"read_as": "34", "actually": "54", "page": 6, "unresolved": True,
                 "message": "engines disagree"}])
    assert ocr_conflict(cov)[0].proposed == ""


def test_a_resolved_misread_is_not_a_question():
    """Only `unresolved` entries are forks. A misread the text already settled has an
    answer, and putting it in a queue of open questions wastes the reviewer's attention
    on work already done."""
    from cairn.ambiguity import ocr_conflict
    assert ocr_conflict(_Cov([{"read_as": "140", "actually": "14a", "page": 3}])) == []


def test_the_pane_says_out_loud_when_there_is_no_recommendation():
    """An absent recommendation and a recommendation nobody rendered look identical on
    the page, and only one of them means "there is genuinely nothing to go on"."""
    from cairn.adjudicate_pane import _ambiguities
    from cairn.ambiguity import ocr_conflict

    cov = _Cov([{"read_as": "36", "actually": "56", "page": 6, "unresolved": True,
                 "message": "engines disagree"}])
    html = _ambiguities(ocr_conflict(cov))
    assert "no recommendation here" in html
    assert "inventing confidence" in html


def _resolution(tmp_path, amb_id, page, readings, bbox, chosen):
    from cairn.adjudication import Adjudication, AdjudicationLog
    from cairn.ambiguity import TARGET_KIND
    log = AdjudicationLog(tmp_path / "adjudications.jsonl")
    log.append(Adjudication(
        adj_id=f"{amb_id}::correct::2026-08-18", kind="correct", target_kind=TARGET_KIND,
        target={"amb_id": amb_id, "page": page, "readings": readings, "bbox": bbox},
        value={"reading": chosen}, by="J. Smith", on="2026-08-18"))
    return log


def test_resolving_a_conflict_reshapes_the_sheet(tmp_path):
    """D84: a ruling that changes nothing downstream is one the reviewer stops making.

    Reading the sheet to settle "is this 12 or 72?" is the most expensive evidence in
    the system — a human looked — and it used to move a row out of a queue and nothing
    else, while the drawings went on showing both readings.
    """
    from cairn.figures_map import apply_adjudications

    _resolution(tmp_path, "ocr_conflict:p6:12-72", 6, ["12", "72"],
                [0.4115, 0.6032, 0.038, 0.021], "72")
    man = {"pages": [{"page": 6, "numerals": [
        {"numeral": "72", "x": 0.4115, "y": 0.6032, "w": .03, "h": .02, "confidence": 1.0},
        {"numeral": "12", "x": 0.4190, "y": 0.6086, "w": .03, "h": .02, "confidence": 0.06},
    ]}]}
    left = apply_adjudications(man, tmp_path)["pages"][0]["numerals"]
    assert [str(n["numeral"]) for n in left] == ["72"]
    kept = left[0]
    assert kept["method"] == "human" and kept["confidence"] == 1.0
    assert kept["by"] == "J. Smith", "a person settled it; provenance must say so"


def test_a_ruling_spares_the_same_label_elsewhere_on_the_sheet(tmp_path):
    """Identity is label PLUS position. Sheet 8 carries a second "92" half a page from
    the disputed mark; a ruling about one must not delete the other. (Checking by label
    alone reported this as a failed ruling three times before the check was fixed —
    the same coarse-instrument error D69 and D81 each hit.)"""
    from cairn.figures_map import apply_adjudications

    _resolution(tmp_path, "ocr_conflict:p8:52-92", 8, ["52", "92"],
                [0.2281, 0.6105, 0.03, 0.02], "52")
    man = {"pages": [{"page": 8, "numerals": [
        {"numeral": "52", "x": 0.2281, "y": 0.6105, "w": .03, "h": .02, "confidence": 0.9},
        {"numeral": "92", "x": 0.2310, "y": 0.6112, "w": .03, "h": .02, "confidence": 0.8},
        {"numeral": "92", "x": 0.8124, "y": 0.6279, "w": .03, "h": .02, "confidence": 1.0},
    ]}]}
    left = apply_adjudications(man, tmp_path)["pages"][0]["numerals"]
    far = [n for n in left if str(n["numeral"]) == "92"]
    assert len(far) == 1 and far[0]["x"] == 0.8124, "the undisputed twin must survive"
    assert not [n for n in left if str(n["numeral"]) == "92" and n["x"] < 0.5]


def test_neither_drops_both_readings(tmp_path):
    """"Neither" is the reviewer saying the ink is something else again — keeping the
    higher-confidence guess would be the machine overruling them."""
    from cairn.figures_map import apply_adjudications

    _resolution(tmp_path, "ocr_conflict:p6:36-56", 6, ["36", "56"],
                [0.5, 0.5, 0.03, 0.02], "neither")
    man = {"pages": [{"page": 6, "numerals": [
        {"numeral": "36", "x": 0.5, "y": 0.5, "w": .03, "h": .02, "confidence": 0.7},
        {"numeral": "56", "x": 0.502, "y": 0.501, "w": .03, "h": .02, "confidence": 0.6},
    ]}]}
    assert apply_adjudications(man, tmp_path)["pages"][0]["numerals"] == []


def test_only_ocr_conflicts_touch_marks(tmp_path):
    """A `numeral_sense` ruling is about the TEXT and a `figure_guess` about an
    assignment; neither is about a mark, and acting on one here would edit a sheet on
    the strength of an assertion nobody made about it."""
    from cairn.figures_map import apply_adjudications

    _resolution(tmp_path, "numeral_sense:20", 2, ["20"], [0.5, 0.5, .03, .02],
                "measurement only")
    man = {"pages": [{"page": 2, "numerals": [
        {"numeral": "20", "x": 0.5, "y": 0.5, "w": .03, "h": .02, "confidence": 0.9}]}]}
    assert len(apply_adjudications(man, tmp_path)["pages"][0]["numerals"]) == 1


def test_two_marks_disputing_the_same_readings_are_two_questions():
    """D86: sheet 13 of the Apple demo carries two 100/1002 conflicts at opposite ends.

    Sharing an `amb_id` is not a cosmetic duplicate. Resolving one would record a
    judgment matching BOTH, drop both from the queue, and leave the second mark
    unreviewed while the record said a human ruled on it — the D69/D84 family again, on
    the one path where exactness is the product.
    """
    from cairn.ambiguity import ocr_conflict

    cov = _Cov([
        {"read_as": "100", "actually": "1002", "page": 13, "unresolved": True,
         "bbox": [0.2628, 0.8052, 0.065, 0.017], "message": "engines disagree"},
        {"read_as": "100", "actually": "1002", "page": 13, "unresolved": True,
         "bbox": [0.2538, 0.2746, 0.065, 0.016], "message": "engines disagree"},
    ])
    ids = [a.amb_id for a in ocr_conflict(cov)]
    assert len(set(ids)) == 2, ids
    assert all("@" in i for i in ids)
    # …and the rows READ differently, so the reviewer can tell them apart on the page
    details = [a.detail for a in ocr_conflict(cov)]
    assert details[0] != details[1]
    assert "0.805" in details[0] or "0.805" in details[1]


def test_the_position_suffix_is_stable_across_rebuilds():
    """It comes from the frozen manifest's coordinates, so a resolution keeps pointing
    at the mark it settled."""
    from cairn.ambiguity import ocr_conflict
    cov = _Cov([{"read_as": "100", "actually": "1002", "page": 13, "unresolved": True,
                 "bbox": [0.2628, 0.8052, 0.065, 0.017], "message": "x"}])
    assert ocr_conflict(cov)[0].amb_id == ocr_conflict(cov)[0].amb_id
    assert ocr_conflict(cov)[0].amb_id.endswith("@2628x8052")


def test_a_legacy_ruling_still_closes_an_unambiguous_ambiguity():
    """Ids gained a suffix; completed review work must not silently reopen."""
    from cairn.ambiguity import _resolved_ids, ocr_conflict
    cov = _Cov([{"read_as": "12", "actually": "72", "page": 6, "unresolved": True,
                 "bbox": [0.4115, 0.6032, 0.038, 0.021], "message": "x"}])
    found = ocr_conflict(cov)
    assert _resolved_ids({"ocr_conflict:p6:12-72"}, found) == {found[0].amb_id}


def test_an_ambiguous_legacy_ruling_reopens_both_rather_than_closing_either():
    """A legacy id covering two marks cannot say which one the reviewer looked at.
    Reopening costs them a second look; closing a mark nobody examined puts their name
    on a judgment they never made. Only one of those errors is recoverable."""
    from cairn.ambiguity import _resolved_ids, ocr_conflict
    cov = _Cov([
        {"read_as": "100", "actually": "1002", "page": 13, "unresolved": True,
         "bbox": [0.2628, 0.8052, 0.065, 0.017], "message": "x"},
        {"read_as": "100", "actually": "1002", "page": 13, "unresolved": True,
         "bbox": [0.2538, 0.2746, 0.065, 0.016], "message": "x"},
    ])
    assert _resolved_ids({"ocr_conflict:p13:100-1002"}, ocr_conflict(cov)) == set()
