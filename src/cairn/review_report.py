"""review_report — the signable record of the inquiry (RT-5).

**What is being sold here.** Not the answer. Under 37 CFR 11.18(b) a practitioner's
certification is **non-delegable**, so the artifact a professional can actually buy is the
*record of the inquiry* — what was searched, what was found, what was rejected, what was
declined, and under exactly what declared limits. The landscape survey found this is what
the one commercially successful comparable monetises, and that Cairn already holds the
substrate no surveyed competitor matches: a hash-chained log, byte-identical replay,
contract-stamped provenance.

**Two wording rules, load-bearing rather than stylistic.** This document must say it
*evidences*, *documents* and *supports* an inquiry — never that it *satisfies*, *ensures*
or *completes* one. A record that implies search breadth it does not have is a liability
artifact, not an asset; retrieval here is a ranked BM25 slice, not an exhaustive search,
and the report says so where a reader cannot miss it. Everything the tool declines to
conclude stays declined (D10: locate & evidence, never adjudicate).

**Structure follows D33's discipline:** the limits arrive *before* the findings. A caveat
a reader meets at the end is a caveat that did not work.

Open intake questions this builds against (stated, not assumed away):
  · **Q13** — which analysis the client wants. This module is deliberately orthogonal:
    it wraps whatever interactions the audit log holds, so answering Q13 changes the
    *content* of a report and not its shape.
  · **Q16** — delivery form. Defaulted to a self-contained HTML page: no server, emailable,
    prints to PDF for signature, and matches every other surface in the repo.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from pathlib import Path

from .calibration import describe as describe_calibration
from .contract import CONTRACT_VERSION


@dataclass
class CorpusIdentity:
    """What was searched, pinned so the reader can verify it independently."""

    doc_ids: list[str]
    hashes: dict[str, str]
    calibration: str            # human-readable calibration state (D44)
    calibrated: bool


@dataclass
class ReportData:
    engagement: str
    corpus: CorpusIdentity
    interactions: list           # evidence_view.Interaction
    entries: list[dict] = field(default_factory=list)   # raw audit payloads
    generated_on: str = ""       # supplied by the caller — cores stay clock-free (I6)
    claims: object | None = None  # claim_record.ClaimsSection, for a patent (D89)


def corpus_identity(store_dir: str | Path, doc_store) -> CorpusIdentity:
    """What was searched, pinned so the reader can verify it independently.

    The calibration verdict comes from `calibration.resolve`, not from a second reading
    of the record here: the client-facing report and the audit log must never disagree
    about whether a floor can be trusted, and two branches over the same fields is how
    they would come to.
    """
    ids = doc_store.list_docs()
    hashes = {d: doc_store.load(d).content_hash for d in ids}
    note, calibrated = describe_calibration(store_dir, ids, [hashes[d] for d in ids])
    return CorpusIdentity(ids, hashes, note, calibrated)


# --- the declared limits ------------------------------------------------------------
# Each is a limit a professional must know to rely on this record correctly. They are
# listed FIRST in the rendered page, and they are phrased as facts about the method
# rather than as disclaimers about liability — a disclaimer invites being read past.

LIMITS: list[tuple[str, str]] = [
    ("This records an inquiry; it does not complete one",
     "The certification under 37 CFR 11.18(b) is non-delegable. This document evidences "
     "and supports the reviewer's inquiry — it does not satisfy, ensure or discharge it."),
    ("Retrieval is a ranked slice, not an exhaustive search",
     "Candidate passages are ranked by BM25 over the listed documents and the top matches "
     "are returned. Nothing here establishes that no other relevant passage exists, in "
     "these documents or outside them."),
    ("A verified citation is real, not necessarily supporting",
     "Verification confirms that each cited span EXISTS at the recorded offsets and that "
     "the document still hashes as it did at ingest. It does not confirm that the span "
     "entails the claim made from it. That judgment remains the reviewer's."),
    ("Nothing here is a legal conclusion",
     "The tool locates and evidences. It does not conclude on novelty, obviousness, "
     "validity, infringement, freedom to operate, or claim construction, and a refusal "
     "to do so is recorded as an outcome in its own right rather than as a failure."),
    ("Drawing locations are OCR-derived",
     "Where a reference numeral is shown located on a drawing sheet, that location is a "
     "machine reading of pixels, frozen at ingestion. It is a reviewer's aid to be "
     "confirmed by eye, never a citation."),
    ("Absence of a flag is not evidence of correctness",
     "The consistency checks compare the drawings against the specification. Anything "
     "absent from both is invisible to all of them. Flag counts are a floor on the "
     "discrepancies present, never a ceiling."),
]


# Limits that apply only when the record carries a claims section (D89). Listed with the
# others, first, for the same reason: a caveat met after the findings has not worked.
CLAIM_LIMITS: list[tuple[str, str]] = [
    ("A passage that resembles a limitation is not support for it",
     "Each claim limitation is shown beside the description passages that share the most "
     "words with it, ranked by BM25. A high rank means shared vocabulary. It does not "
     "establish written description, enablement or any other sufficiency, and a low rank "
     "does not establish their absence."),
    ("The vocabulary check is literal",
     "A limitation word is reported absent only when neither it nor a close form of it (a "
     "plural, or a shared stem of five letters or more) appears anywhere in the "
     "description. Synonyms are not recognised, and the rule errs toward not flagging: it "
     "can miss a difference in wording, but every word it reports absent is absent."),
    ("Dates are reproduced, not interpreted",
     "Front-page dates are shown as printed, with the effective-filing date derived from "
     "them and its basis cited. Term, expiry and maintenance status are not computed; they "
     "depend on facts this document does not contain."),
]


def outcome_counts(interactions: list) -> dict[str, int]:
    counts: dict[str, int] = {}
    for i in interactions:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    return counts


def rejected_candidates(entries: list[dict]) -> list[dict]:
    """Passages retrieval surfaced that were NOT carried into an answer.

    Deliberately included. A record showing only what was used invites the reading that
    nothing else was seen; showing what was surfaced and set aside is what makes the
    inquiry's *shape* auditable, and it is the half a reviewer needs in order to disagree
    with it. `closest` spans on an abstention are the same evidence in the other
    direction — proof that the tool looked, and where.
    """
    out = []
    for e in entries:
        if e.get("kind") not in ("check_support", "check_claim"):
            continue
        for h in e.get("closest", []):
            out.append({"query": e.get("query", ""), "status": e.get("status", ""),
                        "span": h, "warning": e.get("calibration_warning")})
    return out


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _filing_html(f) -> str:
    rows = [("Patent", f.patent_number), ("Date of patent", f.date_of_patent),
            ("Application", f.application_number), ("Filed", f.filed)]
    rows += [("Priority claim", p) for p in f.priority_claims]
    shown = [(k, v) for k, v in rows if v]
    if not shown:
        # Said, not left blank: a missing table and a table nobody rendered look alike.
        return ("<p class='sub'>No front-page fields were found in this document's text, "
                "so no dates are reproduced and no effective-filing date is derived.</p>")
    body = "".join(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in shown)
    r = f.regime
    if r:
        body += (f"<tr><th>Effective filing</th><td>{_esc(r['effective_filing_date'])} "
                 f"<span class='sub'>· basis: “{_esc(r['basis'])}”</span></td></tr>"
                 f"<tr><th>AIA comparison</th><td>{_esc(r['flag'])} — "
                 f"{_esc(r['comparison'])}<br><span class='sub'>{_esc(r['note'])}</span>"
                 f"</td></tr>")
    return f"<table class='kv'>{body}</table>"


def _claims_html(sec) -> str:
    """The claims half of the record (D89). Wording is load-bearing: *resembles*, never
    *supports*; *absent from the description*, never *unsupported* (D10)."""
    from .claim_record import RELATED

    n_ind = sum(1 for c in sec.claims if c.kind == "independent")
    if sec.dependency_issues:
        deps = "<ul>" + "".join(f"<li class='flag'>{_esc(i.message)}</li>"
                                for i in sec.dependency_issues) + "</ul>"
    else:
        deps = ("<p>Every dependent claim refers to a claim that exists and comes before "
                "it.</p>")

    # One row per word, with its plural folded in: "end" and "ends" are one absence, and
    # two rows for it read as two findings. Counted per limitation, not per occurrence.
    absent_all = {w for c in sec.claims for lim in c.limitations for w in lim.absent}

    def _key(w: str) -> str:
        return w[:-1] if w.endswith("s") and w[:-1] in absent_all else w

    tally: dict[str, list[int]] = {}
    shown_as: dict[str, set[str]] = {}
    for c in sec.claims:
        for lim in c.limitations:
            for k in sorted({_key(w) for w in lim.absent}):
                tally.setdefault(k, []).append(c.number)
            for w in lim.absent:
                shown_as.setdefault(_key(w), set()).add(w)
    if tally:
        vocab = "".join(
            f"<tr><td class='mono'>{_esc(' / '.join(sorted(shown_as[w])))}</td>"
            f"<td>{len(ns)}</td>"
            f"<td>{_esc(', '.join(str(n) for n in sorted(set(ns))))}</td></tr>"
            for w, ns in sorted(tally.items(), key=lambda kv: (-len(kv[1]), kv[0])))
        vocab = ("<table><thead><tr><th>Word</th><th>Limitations using it</th>"
                 f"<th>Claims</th></tr></thead><tbody>{vocab}</tbody></table>")
    else:
        vocab = ("<p>Every content word in every limitation appears in the description, "
                 "verbatim or in a related form.</p>")

    blocks = []
    for c in sec.claims:
        head = ("independent" if c.depends_on is None
                else f"depends on claim {c.depends_on}")
        lims = []
        for lim in c.limitations:
            notes = []
            if lim.absent:
                notes.append("<span class='flag'>not in the description in any form: "
                             + _esc(", ".join(lim.absent)) + "</span>")
            rel = [t for t in lim.terms if t.status == RELATED]
            if rel:
                notes.append("<span class='sub'>description's wording: " + _esc("; ".join(
                    f"{t.word} → {', '.join(t.forms[:3])}" for t in rel)) + "</span>")
            n_words = len(lim.terms)
            cands = "".join(
                f"<li><b>{_esc(cd.label)}</b> <span class='mono sm'>"
                f"[{cd.char_start}–{cd.char_end}]</span> · shares {len(cd.shared)} of "
                f"{n_words} words · BM25 {cd.score:g}</li>" for cd in lim.candidates)
            cands = (f"<ul class='cands'>{cands}</ul>" if cands else
                     "<p class='sub'>No description passage shares any word with it.</p>")
            # Built outside the f-string: 3.11 cannot reuse the outer quote inside one.
            notes_html = ("<div class='notes'>" + "<br>".join(notes) + "</div>"
                          if notes else "")
            lims.append(
                f"<li class='lim{' has-flag' if lim.absent else ''}'>"
                f"<div><span class='ln'>{lim.index}</span> {_esc(lim.text)} "
                f"<span class='mono sm mut'>[{lim.char_start}–{lim.char_end}]</span></div>"
                f"{notes_html}"
                f"<div class='sub'>Resembling passages, ranked:</div>{cands}</li>")
        absent_n = sum(1 for lim in c.limitations if lim.absent)
        blocks.append(
            f"<section class='claim'><h3>Claim {c.number} <span class='sub'>· {head} · "
            f"{len(c.limitations)} limitation(s)"
            f"{f' · {absent_n} with absent words' if absent_n else ''} · "
            f"<span class='mono'>[{c.char_start}–{c.char_end}]</span></span></h3>"
            f"<ol class='lims'>{''.join(lims)}</ol></section>")

    return f"""
<h2>The patent as printed</h2>
{_filing_html(sec.filing)}

<h2>Claims and the description</h2>
<p class='sub'>{len(sec.claims)} claims ({n_ind} independent) · {sec.n_limitations}
 limitations · {sec.n_paragraphs} description passages. Each limitation is shown with the
 passages that share the most words with it — where a reviewer starts reading, not a
 finding that the description supports the claim.</p>
<h3>Claim dependencies</h3>
{deps}
<p class='sub'>Where a claim refers to more than one earlier claim, the first reference is
 the one checked.</p>
<h3>Words the claims use that the description never does</h3>
<p class='sub'>In any form. {sec.limitations_with_absent_words} of {sec.n_limitations}
 limitations use at least one. A different word can describe the same thing; this list
 says where the wording differs, not whether the substance does.</p>
{vocab}
{''.join(blocks)}
"""


def render(data: ReportData) -> str:
    """The self-contained HTML report (Q16 default; see module docstring)."""
    c = data.corpus
    counts = outcome_counts(data.interactions)
    rejected = rejected_candidates(data.entries)
    cal_class = "ok" if c.calibrated else "warn"

    limits = "".join(
        f"<li><b>{_esc(t)}.</b> {_esc(body)}</li>"
        for t, body in LIMITS + (CLAIM_LIMITS if data.claims is not None else []))
    claims_html = _claims_html(data.claims) if data.claims is not None else ""

    docs = "".join(
        f"<tr><td class='mono'>{_esc(d)}</td>"
        f"<td class='mono hash'>{_esc(c.hashes[d])}</td></tr>" for d in c.doc_ids)

    order = ["answer", "correction", "partial", "abstain", "refuse"]
    chips = "".join(
        f"<span class='chip {k}'>{counts.get(k, 0)} {k}</span>"
        for k in order if counts.get(k))

    rows = []
    for n, i in enumerate(data.interactions, 1):
        cited = []
        if i.verify is not None:
            for s in i.verify.sentences:
                for a in s.atom_verdicts:
                    b = a.binding
                    cited.append(f"{b.doc_id} [{b.char_start}–{b.char_end}] "
                                 f"“{b.text}” · {a.status}")
        body = "<br>".join(_esc(x) for x in cited) or "<i>no citation presented</i>"
        ok = "—" if i.verify is None else ("verified" if i.verify.ok else "NOT verified")
        rows.append(
            f"<tr><td>{n}</td><td>{_esc(i.question)}</td>"
            f"<td><span class='chip {_esc(i.kind)}'>{_esc(i.kind)}</span></td>"
            f"<td class='mono sm'>{body}</td><td>{_esc(ok)}</td></tr>")
    interactions_html = "".join(rows) or (
        "<tr><td colspan='5'><i>No interactions recorded in this segment.</i></td></tr>")

    rej = "".join(
        f"<tr><td>{_esc(r['query'])}</td><td>{_esc(r['status'])}</td>"
        f"<td class='mono sm'>{_esc(json.dumps(r['span'])[:160])}</td></tr>"
        for r in rejected[:60])
    rej_html = rej or "<tr><td colspan='3'><i>None recorded.</i></td></tr>"

    return _PAGE.format(
        engagement=_esc(data.engagement), generated=_esc(data.generated_on or "—"),
        contract=_esc(CONTRACT_VERSION), limits=limits, docs=docs,
        cal_class=cal_class, calibration=_esc(c.calibration),
        chips=chips or "<span class='chip'>no interactions</span>",
        interactions=interactions_html, rejected=rej_html, claims=claims_html,
        n_rejected=len(rejected), n_docs=len(c.doc_ids),
        n_interactions=len(data.interactions))


_PAGE = """<meta charset="utf-8"><title>Record of inquiry — {engagement}</title>
<style>
:root{{--ink:#12161f;--mut:#5b6577;--rule:#d8dae1;--bg:#fbfbfc;--warn:#a8322c;
 --warnbg:#fdf3f2;--ok:#2f6b4f;--okbg:#eff6f2;--accent:#2f4f8f}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 Georgia,"Iowan Old Style",serif}}
main{{max-width:920px;margin:0 auto;padding:0 28px 80px}}
h1{{font:600 30px/1.2 ui-sans-serif,system-ui,sans-serif;margin:44px 0 4px}}
h2{{font:600 17px/1.3 ui-sans-serif,system-ui,sans-serif;margin:38px 0 10px;
 padding-bottom:6px;border-bottom:1px solid var(--rule)}}
.sub{{color:var(--mut);font:13px/1.5 ui-sans-serif,system-ui,sans-serif;margin:0 0 8px}}
.limits{{border:1px solid var(--warn);border-left:5px solid var(--warn);
 background:var(--warnbg);border-radius:6px;padding:16px 20px;margin:22px 0}}
.limits h2{{border:0;margin:0 0 8px;padding:0;color:var(--warn);font-size:15px;
 text-transform:uppercase;letter-spacing:.05em}}
.limits ul{{margin:0;padding-left:20px}}
.limits li{{margin:9px 0;font-size:14px}}
table{{border-collapse:collapse;width:100%;font:13.5px/1.5 ui-sans-serif,system-ui,sans-serif}}
th,td{{text-align:left;padding:8px 12px 8px 0;border-bottom:1px solid var(--rule);
 vertical-align:top}}
th{{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}}
.mono{{font-family:ui-monospace,"SF Mono",Menlo,monospace}}
.sm{{font-size:12px}} .hash{{font-size:11px;color:var(--mut);word-break:break-all}}
.chip{{display:inline-block;padding:2px 9px;border-radius:11px;font:600 11.5px/1.7
 ui-sans-serif,system-ui,sans-serif;background:#e9ecf3;color:#33405c;margin-right:5px}}
.chip.answer{{background:#e6efe9;color:var(--ok)}}
.chip.correction{{background:#fdf3e6;color:#8a5a12}}
.chip.partial{{background:#eef0f6;color:#3f4a63}}
.chip.abstain{{background:#eceef2;color:#5b6577}}
.chip.refuse{{background:var(--warnbg);color:var(--warn)}}
.state{{border-radius:6px;padding:11px 15px;margin:12px 0;font-size:13.5px;
 font-family:ui-sans-serif,system-ui,sans-serif}}
.state.ok{{background:var(--okbg);border:1px solid #bcd8c8}}
.state.warn{{background:var(--warnbg);border:1px solid #e6b3ae;color:var(--warn)}}
h3{{font:600 15px/1.35 ui-sans-serif,system-ui,sans-serif;margin:24px 0 8px}}
table.kv th{{width:170px;text-transform:none;letter-spacing:0;font-size:13px}}
.flag{{color:var(--warn)}}
.mut{{color:var(--mut)}}
.claim{{border-top:1px solid var(--rule);margin-top:22px;break-inside:avoid-page}}
.claim h3 .sub{{font-weight:400}}
ol.lims{{list-style:none;padding:0;margin:0}}
.lim{{padding:10px 0 10px 14px;border-left:3px solid var(--rule);margin:8px 0}}
.lim.has-flag{{border-left-color:var(--warn)}}
.lim .ln{{display:inline-block;min-width:1.6em;font:600 12px ui-monospace,Menlo,monospace;
 color:var(--mut)}}
.notes{{margin:5px 0;font:13px/1.5 ui-sans-serif,system-ui,sans-serif}}
ul.cands{{margin:3px 0 0;padding-left:20px;font:13px/1.6 ui-sans-serif,system-ui,sans-serif}}
.sign{{margin-top:44px;border-top:2px solid var(--ink);padding-top:16px;
 font:13.5px/1.9 ui-sans-serif,system-ui,sans-serif}}
.sign .line{{display:inline-block;border-bottom:1px solid var(--ink);
 min-width:290px;margin:0 12px}}
</style>
<main>
<h1>Record of inquiry</h1>
<p class="sub">{engagement} · generated {generated} · truth contract v{contract} ·
 {n_docs} document(s) · {n_interactions} interaction(s)</p>

<div class="limits">
  <h2>Read before relying on this record</h2>
  <ul>{limits}</ul>
</div>

<h2>What was searched</h2>
<p class="sub">Content hashes are recorded at ingest. Re-hashing a document and comparing
 it against the value below verifies, independently of this tool, that the text examined
 is the text you hold.</p>
<table><thead><tr><th>Document</th><th>SHA-256 at ingest</th></tr></thead>
<tbody>{docs}</tbody></table>
<div class="state {cal_class}">{calibration}</div>
{claims}
<h2>Outcomes</h2>
<p class="sub">Every interaction resolves to one of five recorded outcomes. A refusal to
 reach a legal conclusion, and an abstention for want of evidence, are outcomes in their
 own right — not failures, and not silence.</p>
<p>{chips}</p>
<table><thead><tr><th>#</th><th>Question</th><th>Outcome</th>
 <th>Citations (document, offsets, literal, status)</th><th>Verification</th></tr></thead>
<tbody>{interactions}</tbody></table>

<h2>Surfaced and set aside ({n_rejected})</h2>
<p class="sub">Passages retrieval returned that were not carried into an answer, and the
 nearest passages found where the tool abstained. Included so the shape of the inquiry is
 auditable — and so a reviewer has what they need in order to disagree with it.</p>
<table><thead><tr><th>Query</th><th>Status</th><th>Passage</th></tr></thead>
<tbody>{rejected}</tbody></table>

<div class="sign">
  <p>The reviewer below has examined this record and the sources it cites. The
  certification required by 37 CFR 11.18(b) rests with that reviewer; this document
  evidences the inquiry undertaken and does not discharge it.</p>
  <p>Reviewer <span class="line"></span> Date <span class="line"></span></p>
</div>
</main>
"""
