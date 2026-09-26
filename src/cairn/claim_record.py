"""claim_record — the claims half of the Record of Inquiry (PE-2/PE-3/PE-4, D89).

The engagement's deliverable is a signable record of inquiry (D46), and the analysis the
tailoring doc calls primary is claim → specification (§6.1). The pieces existed —
`parse_claims`, `decompose_claim`, `map_claim_support`, `check_dependencies`,
`parse_front_matter`, `regime_flag` — but reached no surface a professional is handed.
This module assembles them into one deterministic, offset-addressed section.

**What it says, and what it refuses to say (D10).** Every statement here is one a
reviewer can check by reading:

  · the front-page facts, *as printed*, with the effective-filing derivation and its
    verbatim basis. Term, expiry and maintenance status are NOT computed: they turn on
    facts outside the document, and computing them would be adjudication.
  · the claim structure and whether each dependency points at an existing earlier claim.
  · for each limitation, the description passages that share the most words with it,
    ranked. **Resemblance, not support.** Shared vocabulary is where a reviewer starts
    reading; it never establishes written description, enablement or anything else.
  · for each limitation, which of its own words the description uses — verbatim, only
    in a related form, or in no form at all.

**Why the vocabulary check, and why this rule.** `map_claim_support` has no calibrated
floor, so it returns a "best" paragraph for every limitation, however weak (scores on the
engagement patent run from 3 to 520). Presenting that as located support would overstate
on every row, and its one gap signal — an empty list — never fires. A literal word check
gives the reviewer a signal they can verify by eye. Measured on the engagement patent
(2026-09-26): with verbatim matching alone, 47 of 53 limitations flagged, almost all on
tense and form ("receiving" vs "received") — the D58 failure, a defect-shaped flag that is
mostly wrong. With related forms recognised, the remaining flags are words genuinely
absent from the description in every form. The rule errs toward NOT flagging: a spurious
family ("relative" ~ "relates") hides a gap; nothing here invents one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .patents import (
    StructuralIssue,
    check_dependencies,
    decompose_claim,
    map_claim_support,
    parse_claims,
    parse_front_matter,
    parse_paragraphs,
    regime_flag,
)
from .retrieval import STOPWORDS

# Whole words, keeping hyphenated compounds whole. Splitting "end-products" into parts
# would let the claim's "ends" match the description's "end-products" — a false family.
_WORD = re.compile(r"[a-z]+(?:-[a-z]+)*")

# Claim drafting vocabulary that says nothing about the invention. Kept here, not in
# `retrieval.STOPWORDS`, for the same reason `question_lint` keeps its own list: changing
# the retriever's stoplist changes every BM25 score in the system.
_CLAIM_BOILERPLATE = frozenset(
    "said wherein claim claims means comprising comprises including includes having "
    "whereby thereof therein therewith thereby further least plurality one first second "
    "third each such being which within between onto upon where whereof".split())

VERBATIM, RELATED, ABSENT = "verbatim", "related", "absent"

# A related form shares a stem of at least this many letters. Five keeps "remov-" and
# "extend-" while refusing three- and four-letter coincidences.
_MIN_STEM = 5


def content_words(text: str) -> list[str]:
    """The limitation's own words — what a reviewer would look for in the description."""
    seen: dict[str, None] = {}
    for w in _WORD.findall(text.lower()):
        if len(w) > 2 and w not in STOPWORDS and w not in _CLAIM_BOILERPLATE:
            seen.setdefault(w, None)
    return list(seen)


def _related_forms(word: str, vocab: frozenset[str]) -> tuple[str, ...]:
    """Description words that are plausibly the same word in another form.

    Two rules, both legible: a plural ("ends" → "end"), and a shared stem of the word
    minus up to three letters, never shorter than `_MIN_STEM` ("receiving" → "received",
    "separator" → "separation"). Words shorter than six letters get the plural rule
    only — "axis" and "path" have no stem short enough to be safe.
    """
    forms = set()
    if word.endswith("s") and word[:-1] in vocab:
        forms.add(word[:-1])
    if len(word) >= _MIN_STEM + 1:
        stem = word[:max(_MIN_STEM, len(word) - 3)]
        forms.update(v for v in vocab if v.startswith(stem) and v != word)
    return tuple(sorted(forms))


@dataclass(frozen=True)
class TermCheck:
    word: str
    status: str                  # VERBATIM | RELATED | ABSENT
    forms: tuple[str, ...] = ()  # the description's forms, when RELATED


def check_terms(words: list[str], vocab: frozenset[str]) -> tuple[TermCheck, ...]:
    out = []
    for w in words:
        if w in vocab:
            out.append(TermCheck(w, VERBATIM))
        else:
            forms = _related_forms(w, vocab)
            out.append(TermCheck(w, RELATED, forms) if forms else TermCheck(w, ABSENT))
    return tuple(out)


def _vocab(text: str) -> frozenset[str]:
    return frozenset(_WORD.findall(text.lower()))


@dataclass(frozen=True)
class Candidate:
    """A description passage that resembles a limitation. Never "support" (D10)."""

    label: str                   # native paragraph label, "[0042]" or "¶12"
    score: float                 # BM25, reported so the ranking can be audited
    char_start: int
    char_end: int
    shared: tuple[str, ...]      # the limitation's words this passage contains, any form


@dataclass(frozen=True)
class LimitationRow:
    index: int                   # 1-based, as a reviewer counts
    text: str
    char_start: int
    char_end: int
    terms: tuple[TermCheck, ...]
    candidates: tuple[Candidate, ...]

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(t.word for t in self.terms if t.status == ABSENT)


@dataclass(frozen=True)
class ClaimRow:
    number: int
    kind: str
    depends_on: int | None
    char_start: int
    char_end: int
    limitations: tuple[LimitationRow, ...]


@dataclass(frozen=True)
class FilingFacts:
    """Front-page facts, verbatim. Nothing derived except the effective-filing date,
    which carries its basis."""

    patent_number: str | None
    date_of_patent: str | None
    application_number: str | None
    filed: str | None
    priority_claims: tuple[str, ...]
    regime: dict | None          # patents.regime_flag, with its basis and its D10 note


@dataclass(frozen=True)
class ClaimsSection:
    doc_id: str
    filing: FilingFacts
    claims: tuple[ClaimRow, ...]
    dependency_issues: tuple[StructuralIssue, ...]
    n_paragraphs: int

    @property
    def n_limitations(self) -> int:
        return sum(len(c.limitations) for c in self.claims)

    @property
    def limitations_with_absent_words(self) -> int:
        return sum(1 for c in self.claims for lim in c.limitations if lim.absent)


def build(doc_id: str, text: str, *, k: int = 2) -> ClaimsSection | None:
    """The claims section for one patent, or None when the document has no claims.

    `text` must be the hash-verified canonical text (`SpanStore.get_document`), so every
    offset below resolves against the document the record's hash table names (I1/I3).
    """
    claims = parse_claims(text)
    if not claims:
        return None
    paragraphs = parse_paragraphs(text)
    desc_vocab = _vocab(" ".join(p.text for p in paragraphs))
    para_vocab = {p.char_start: _vocab(p.text) for p in paragraphs}
    by_start = {p.char_start: p for p in paragraphs}

    rows = []
    for c in claims:
        mapped = dict((lim.index, edges) for lim, edges in
                      map_claim_support(c, paragraphs, doc_id, k=k))
        lims = []
        for lim in decompose_claim(c):
            words = content_words(lim.text)
            cands = []
            for e in mapped.get(lim.index, []):
                pv = para_vocab[e.char_start]
                shared = tuple(w for w in words
                               if w in pv or _related_forms(w, pv))
                cands.append(Candidate(by_start[e.char_start].label, e.score,
                                       e.char_start, e.char_end, shared))
            lims.append(LimitationRow(lim.index + 1, lim.text, lim.char_start,
                                      lim.char_end, check_terms(words, desc_vocab),
                                      tuple(cands)))
        rows.append(ClaimRow(c.number, c.kind, c.depends_on, c.char_start, c.char_end,
                             tuple(lims)))

    fm = parse_front_matter(text)
    filing = FilingFacts(fm.patent_number, fm.date_of_patent, fm.application_number,
                         fm.filed, tuple(fm.priority_claims), regime_flag(fm))
    return ClaimsSection(doc_id, filing, tuple(rows), tuple(check_dependencies(claims)),
                         len(paragraphs))
