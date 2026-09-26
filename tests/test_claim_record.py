"""Standing tests for the claims half of the Record of Inquiry (D89).

All over the TRACKED synthetic patent, so they run in CI — the engagement patent is
local-only, and a check that only ever runs on one machine is not a gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cairn import claim_record as CR
from cairn.review_report import CorpusIdentity, ReportData, render

pytestmark = pytest.mark.layer0

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = (ROOT / "corpus" / "samples" / "sample_patent.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section():
    return CR.build("SAMPLE", SAMPLE)


def _report(claims) -> str:
    corpus = CorpusIdentity(["SAMPLE"], {"SAMPLE": "0" * 64}, "calibrated", True)
    return render(ReportData("Test engagement", corpus, [], claims=claims,
                             generated_on="2026-09-26"))


def test_every_offset_resolves_to_the_text_it_names(section):
    """I1/I3: the record publishes the document's hash; every claim, limitation and
    candidate passage must slice back to exactly what the record says is there."""
    assert section.claims
    for c in section.claims:
        assert SAMPLE[c.char_start:c.char_end].lstrip().startswith(f"{c.number}.")
        for lim in c.limitations:
            assert SAMPLE[lim.char_start:lim.char_end] == lim.text
            for cd in lim.candidates:
                assert 0 <= cd.char_start < cd.char_end <= len(SAMPLE)
                assert cd.label in SAMPLE[cd.char_start:cd.char_end] or \
                    cd.label.startswith("¶")


def test_structure_matches_the_fixture(section):
    assert [(c.number, c.depends_on) for c in section.claims] == \
        [(1, None), (2, 1), (3, 2), (4, None), (5, 4)]
    assert section.dependency_issues == ()


def test_filing_facts_are_verbatim_and_carry_their_basis(section):
    f = section.filing
    assert f.filed == "Mar. 15, 2021" and f.date_of_patent == "Jan. 2, 2024"
    # The effective-filing date is the one derived value, and it cites its source.
    assert f.regime["effective_filing_date"] == "2020-03-20"
    assert "62/900,000" in f.regime["basis"]


def test_the_three_vocabulary_outcomes():
    vocab = frozenset({"received", "fluid", "end-products", "chamber", "chambers",
                       "relates"})
    got = {t.word: t for t in CR.check_terms(
        ["fluid", "receiving", "tapered", "ends", "chambers", "chamber"], vocab)}
    assert got["fluid"].status == CR.VERBATIM
    assert got["receiving"].status == CR.RELATED and got["receiving"].forms == ("received",)
    assert got["tapered"].status == CR.ABSENT
    # A hyphenated compound is one word: "end-products" does not supply "end(s)".
    assert got["ends"].status == CR.ABSENT


def test_short_words_get_the_plural_rule_only():
    """"axis" / "path" have no stem short enough to be safe; a four-letter prefix would
    call half the dictionary related."""
    vocab = frozenset({"pathway", "axes", "tube"})
    got = {t.word: t.status for t in CR.check_terms(["path", "axis", "tubes"], vocab)}
    assert got == {"path": CR.ABSENT, "axis": CR.ABSENT, "tubes": CR.RELATED}


def test_claim_boilerplate_is_not_a_content_word():
    words = CR.content_words("said chamber, wherein the plurality of first valves")
    assert words == ["chamber", "valves"]


def test_a_forward_dependency_is_surfaced_as_a_fact():
    text = SAMPLE.replace("device of claim 1, wherein the sprocket",
                          "device of claim 7, wherein the sprocket")
    assert text != SAMPLE, "the fixture changed; this test would check nothing"
    sec = CR.build("SAMPLE", text)
    assert [i.claim_number for i in sec.dependency_issues] == [2]
    assert "does not exist" in _report(sec)


def test_no_claims_means_no_section():
    assert CR.build("X", "An annual report with no claims section.") is None
    assert "Claims and the description" not in _report(None)


def test_the_claims_limits_arrive_before_the_findings(section):
    html = _report(section)
    for title, _ in [*__import__("cairn.review_report", fromlist=["x"]).CLAIM_LIMITS]:
        assert title in html
    assert html.index("is not support for it") < html.index("Claims and the description")
    # The claims come before the Q&A: they are the primary analysis (tailoring §6.1).
    assert html.index("Claims and the description") < html.index("<h2>Outcomes</h2>")


def test_the_claims_limits_appear_only_with_a_claims_section():
    assert "is not support for it" not in _report(None)


def test_the_section_never_concludes(section):
    """D10, as wording: the section says *resembles* and *absent from the description*.
    It must never say a limitation is supported, unsupported, sufficient, valid, or that
    the patent has expired — those are the professional's calls."""
    html = _report(section)
    body = html[html.index("The patent as printed"):html.index("<h2>Outcomes</h2>")]
    for banned in (r"\bis supported\b", r"\bunsupported\b", r"\bsupport located\b",
                   r"\bsufficien", r"\binvalid", r"\bexpir", r"\binfring",
                   r"\banticipat", r"\bobvious"):
        assert not re.search(banned, body, re.I), banned


def test_a_missing_front_page_is_said_not_left_blank():
    text = re.sub(r"(?s)^.*?(?=ABSTRACT|DESCRIPTION|\[0001\])", "", SAMPLE, count=1)
    sec = CR.build("SAMPLE", text)
    assert sec.filing.filed is None
    assert "No front-page fields were found" in _report(sec)


def test_absent_words_are_tallied_once_per_limitation(section):
    html = _report(section)
    assert "Words the claims use that the description never does" in html
    assert section.limitations_with_absent_words <= section.n_limitations


def test_a_word_and_its_plural_are_one_row_in_the_summary():
    """"end" and "ends" absent from the description are one difference in wording; two
    rows would read as two findings."""
    from cairn.claim_record import (
        ABSENT,
        ClaimRow,
        ClaimsSection,
        FilingFacts,
        LimitationRow,
        TermCheck,
    )

    def lim(i, *words):
        return LimitationRow(i, "x", 0, 1, tuple(TermCheck(w, ABSENT) for w in words), ())

    sec = ClaimsSection("SAMPLE", FilingFacts(None, None, None, None, (), None),
                        (ClaimRow(1, "independent", None, 0, 1,
                                  (lim(1, "end"), lim(2, "ends", "end"), lim(3, "ends"))),),
                        (), 1)
    html = _report(sec)
    assert "<td class='mono'>end / ends</td><td>3</td>" in html
    assert "<td class='mono'>ends</td>" not in html
