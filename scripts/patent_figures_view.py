#!/usr/bin/env python3
"""Patent drawings review artifact (RT-4) → figures visible beside the text index.

Renders a self-contained HTML page: the patent's **drawing sheets** on the left, and
on the right the parsed **figure captions** (`parse_figures`) and the **reference-
numeral legend** (`reference_numerals`) — each numeral annotated with the figure it is
**first discussed with** (nearest preceding `FIG. N` reference in the text). Click a
figure to filter the legend to its numerals; click a numeral to see its first-mention
context. The sheets are embedded as data URIs (server-less, like the evidence view).

Prereqs (local-only): the drawing images fetched by `scripts/fetch_patent_figures.py`
into `<store>/../figures/`. The engagement store + figures are gitignored, so this is
a local reviewable artifact (the generator is generic; point it at any ingested
patent that has fetched figures).

    python scripts/patent_figures_view.py --store corpus/engagements/US5447630A/store \\
        --doc US5447630A --out figures_view.html

**Truth-contract boundary (D21):** a drawing is *displayed evidence*, not a text
citation — the numeral→figure link is "first discussed near FIG. N" in the text, a
locate-only aid (D10), never a claim about what a figure depicts or construes.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from cairn.figures_map import (
    ELIMINATION,
    HUMAN,
    OCR,
    fig_to_sheets,
    is_locatable,
    load_manifest,
    numeral_coverage,
    numeral_figures,
    numeral_sightings,
    reviewed_numerals,
    sub_figure_parent,
    view_marker_letters,
)
from cairn.ingest import DocumentStore
from cairn.patents import (
    Numeral,
    acronym_labels,
    dimension_labels,
    figure_references,
    parse_figures,
)
from cairn.spans import SpanStore

_NEAR = 500          # a numeral is "discussed with" the nearest FIG ref within this


def numeral_figure(numeral_start: int, fig_refs) -> str | None:
    """The figure a numeral is first discussed with: the nearest FIG. N reference at
    or before the numeral's first mention, within _NEAR chars. Locate-only."""
    best = None
    for r in fig_refs:
        if r.char_start <= numeral_start and numeral_start - r.char_start <= _NEAR:
            if best is None or r.char_start > best.char_start:
                best = r
    return best.number if best else None


def snippet(text: str, start: int, end: int, pad: int = 90) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    pre, hit, post = text[s:start], text[start:end], text[end:e]
    return (("…" if s else "") + html.escape(pre) + "<b>" + html.escape(hit) + "</b>"
            + html.escape(post) + ("…" if e < len(text) else ""))


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
:root{{--bg:#0d1117;--panel:#161b22;--panel2:#1c2230;--bd:#30363d;--tx:#c9d1d9;
--mut:#8b949e;--acc:#58a6ff;--fig:#f0883e;--num:#3fb950}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}}
header{{padding:20px 24px;border-bottom:1px solid var(--bd)}}
h1{{margin:0 0 3px;font-size:20px;letter-spacing:-.3px}}
.sub{{color:var(--mut);font-size:13px}}
.cols{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);
gap:0;height:calc(100vh - 70px)}}
.pane{{overflow:auto;padding:18px 22px}}
.pane.left{{border-right:1px solid var(--bd);background:#0b0f16}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);
margin:0 0 12px;font-weight:700}}
.sheet{{margin:0 0 16px}}
.sheet .cap{{font-size:11px;color:var(--mut);font-family:ui-monospace,monospace;margin-bottom:5px}}
.imgwrap{{position:relative;line-height:0}}
.sheet img{{width:100%;border:1px solid var(--bd);border-radius:8px;background:#fff;display:block}}
.ov{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}
.ov .bx{{fill:none;stroke:transparent;stroke-width:0.006}}
.ov .bx.on{{stroke:#ff3b30;fill:rgba(255,59,48,0.16)}}
.toggle{{font:inherit;font-size:11px;margin-left:8px;background:var(--panel2);color:var(--num);
border:1px solid var(--bd);border-radius:6px;padding:2px 9px;cursor:pointer;vertical-align:middle}}
.toggle:hover{{border-color:var(--num)}}
.mut{{color:var(--mut)}}
.only-all{{display:none}}
body.mode-all .only-all{{display:inline}}
body.mode-all .only-first{{display:none}}
.fig{{background:var(--panel);border:1px solid var(--bd);border-left:3px solid var(--fig);
border-radius:8px;padding:11px 13px;margin:0 0 9px;cursor:pointer;transition:.12s}}
.fig:hover{{border-color:var(--fig)}}
.fig.sel{{background:#2a1c12;border-left-width:5px}}
.fig .fl{{font-weight:700;color:var(--fig);font-family:ui-monospace,monospace}}
.fig .fd{{color:var(--tx);font-size:13px;margin-top:2px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px}}
.num{{background:var(--panel);border:1px solid var(--bd);border-radius:6px;
padding:4px 9px;font-size:12.5px;cursor:pointer;transition:.12s;white-space:nowrap}}
.num:hover{{border-color:var(--num)}}
.num.dim{{opacity:.28}}
.num b{{color:var(--num);font-family:ui-monospace,monospace}}
.num .fg{{color:var(--fig);font-family:ui-monospace,monospace;font-size:11px;margin-left:4px}}
.sh{{color:var(--num);font-family:ui-monospace,monospace;font-size:10.5px;margin-left:5px;
cursor:pointer;border:1px solid var(--bd);border-radius:4px;padding:0 4px}}
.sh:hover{{border-color:var(--num)}}
.sh.tg{{color:var(--fig);border-style:dashed}}   /* recovered by the text-guided pass */
.sh.hu{{color:#d2a8ff;border-style:dotted}}      /* human/visually confirmed (OCR-blind) */
.sh.to{{color:var(--mut);border-style:dotted;cursor:default}} /* text-only (D30) */
.pe2{{color:var(--mut);font-size:12px;line-height:1.55;padding-left:18px;margin:0}}
.pe2 li{{margin:0 0 6px}}
#ctx{{position:sticky;bottom:0;background:#0b0f16f2;border:1px solid var(--bd);
border-radius:8px;padding:11px 13px;font-size:12.5px;min-height:20px;color:var(--mut)}}
#ctx b{{color:var(--tx);background:#243; padding:0 2px;border-radius:3px}}
.note{{color:var(--mut);font-size:11.5px;margin:14px 0 0;line-height:1.5}}
/* The OCR caveat leads the page on purpose: this is the least reliable step in
   CAIRN, and a caveat discovered at the bottom is a caveat that did not work. */
.alarm{{border:1px solid #f85149;border-left:5px solid #f85149;background:#2a1416;
  border-radius:8px;padding:13px 16px;margin:0 0 16px;font-size:12.5px;line-height:1.55}}
.alarm h2{{margin:0 0 7px;font-size:14px;color:#ff9a92;letter-spacing:.02em}}
.alarm .tally{{margin:9px 0 0;padding:0;list-style:none;
  display:flex;flex-wrap:wrap;gap:6px}}
.alarm .tally li{{background:#3a1d20;border:1px solid #6b2b2b;border-radius:5px;
  padding:3px 9px;font-size:12px;color:#ffc9c4}}
.alarm .tally li.zero{{background:#16241a;border-color:#2b5c33;color:#8fd39b}}
.alarm .fine{{color:#d6a8a3;font-size:11.5px;margin:9px 0 0;line-height:1.5}}
.alarm a{{color:#ff9a92}}
</style></head><body>
<h2 class="sr-only">{title}: drawing sheets beside parsed figure captions and numerals.</h2>
<header><h1>{h1}</h1><div class="sub">{sub}</div></header>
{banner}
<div class="cols">
  <div class="pane left"><h2>Drawing sheets ({nsheets})</h2>{sheets}</div>
  <div class="pane right">
    <h2>Figures ({nfigs})</h2>{figs}
    <h2 style="margin-top:20px">Reference numerals ({nnums})
      <button id="mode" class="toggle"
        title="nearest text mention vs every figure it appears in">show: first discussed</button>
    </h2>
    <div class="legend" id="legend">{nums}</div>
    <div id="ctx">Click a numeral to see where it is first named; click a figure to filter.</div>
    {issues}
    <p class="note">{note}</p>
  </div>
</div>
<script>
const CTX = {ctx_json};
const ctx = document.getElementById('ctx');
let selFig = null;
// a numeral matches a figure if it's the first-discussed OR (all-mode) among all its figures
function matches(n, fig){{
  return n.dataset.fig===fig || (n.dataset.figs||'').split(',').includes(fig);
}}
function filter(fig){{
  selFig = (selFig===fig)?null:fig;
  document.querySelectorAll('.fig').forEach(f=>f.classList.toggle('sel', f.dataset.fig===selFig));
  document.querySelectorAll('.num').forEach(n=>
    n.classList.toggle('dim', selFig && !matches(n, selFig)));
  ctx.innerHTML = selFig ? `Numerals appearing in <b>FIG. ${{selFig}}</b> (undimmed).`
    : 'Click a numeral to box it on its sheet(s); click a figure to filter.';
}}
let boxedNum = null;                 // the numeral whose boxes are currently shown
function clearBoxes(){{
  document.querySelectorAll('.ov .bx.on').forEach(b=>b.classList.remove('on'));
  boxedNum = null;
}}
document.querySelectorAll('.fig').forEach(f=>f.addEventListener('click',()=>filter(f.dataset.fig)));
document.querySelectorAll('.num').forEach(n=>n.addEventListener('click',()=>{{
  // click a numeral to box it on every sheet; click it AGAIN to turn the boxes off
  if(boxedNum === n.dataset.n){{ clearBoxes(); ctx.innerHTML = '(boxes off)'; return; }}
  ctx.innerHTML = CTX[n.dataset.n] || '(no context)';
  clearBoxes();
  const rects = document.querySelectorAll('.ov .bx[data-n="'+n.dataset.n+'"]');
  rects.forEach(r=>r.classList.add('on'));
  boxedNum = n.dataset.n;
  if(rects.length) rects[0].closest('.sheet').scrollIntoView({{behavior:'smooth', block:'start'}});
}}));
document.querySelectorAll('.sh').forEach(t=>t.addEventListener('click',e=>{{
  e.stopPropagation();                                 // don't also trigger the numeral toggle
  clearBoxes();
  const sheet = document.getElementById('sheet-'+t.dataset.page);
  // jump to THIS numeral's box on THIS sheet (not just scroll to the page)
  const rect = sheet && sheet.querySelector('.ov .bx[data-n="'+t.dataset.n+'"]');
  if(rect) rect.classList.add('on');
  boxedNum = t.dataset.n;
  if(sheet) sheet.scrollIntoView({{behavior:'smooth', block:'start'}});
}}));
const modeBtn=document.getElementById('mode');
modeBtn.addEventListener('click',()=>{{
  const all=document.body.classList.toggle('mode-all');
  modeBtn.textContent = all ? 'show: all figures' : 'show: first discussed';
}});
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a patent's drawings + figure index (RT-4)")
    ap.add_argument("--store", required=True)
    ap.add_argument("--doc", required=True)
    ap.add_argument("--out", default="figures_view.html")
    ns = ap.parse_args()

    store = SpanStore.from_store(DocumentStore(ns.store))
    text = store.get_document(ns.doc)
    figs = parse_figures(text)
    refs = figure_references(text)
    fig_dir = Path(ns.store).parent / "figures"
    nums = reviewed_numerals(text, fig_dir)       # after the reviewer's rulings (D84/D87)
    manifest_path = fig_dir / "figures_manifest.json"
    if not manifest_path.exists():
        print(f"no figures manifest at {manifest_path} — run scripts/fetch_patent_figures.py first")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # D28: the OCR manifest (if present) supplies FIG→sheet + numeral→sheet ground
    # truth; without it the view falls back to text-proximity tags alone.
    assignments, sightings_by_num = {}, {}
    all_figs_by_num, boxes_by_page, cov = {}, {}, None
    if (fig_dir / "ocr_manifest.json").exists():
        ocr = load_manifest(ns.store)
        known = sorted({f.number for f in figs} | {r.number for r in refs})
        assign_list = fig_to_sheets(ocr, known)
        assignments = {a.fig: a for a in assign_list}
        sights = numeral_sightings(ocr)
        for s in sights:
            sightings_by_num.setdefault(s.numeral, []).append(s)
            if s.bbox is not None:                          # for the confirmation overlay
                boxes_by_page.setdefault(s.page, []).append((s.numeral, s.bbox, s.confidence))
        all_figs_by_num = numeral_figures(assign_list, sights)  # every figure a numeral appears in
        # Reconcile text↔drawings. Sighted ACRONYM labels (STM) count as recited —
        # they are recited, just not by reference_numerals (which is numeral-shaped);
        # without this they false-flag as "drawn but never recited".
        recited_for_cov = list(nums) + [
            Numeral(a, "(text label)", 0, 0)
            for a in acronym_labels(text) + dimension_labels(text) if a in sightings_by_num
        ]
        cov = numeral_coverage(recited_for_cov, text, refs, assign_list, sights)

    def _overlay(page: int) -> str:
        # SVG rects over the sheet (viewBox 0..1, preserveAspectRatio none so it
        # stretches to the img). OCR bbox is origin BOTTOM-left → y_svg = 1 - y - h.
        # A small pad makes the confirmation box sit clearly AROUND the number.
        pad = 0.008
        rects = "".join(
            f'<rect class="bx" data-n="{num}" x="{x - pad:.4f}" y="{1 - y - h - pad:.4f}" '
            f'width="{w + 2 * pad:.4f}" height="{h + 2 * pad:.4f}" rx="0.006">'
            f'<title>{num} (OCR conf {c})</title></rect>'
            for num, (x, y, w, h), c in boxes_by_page.get(page, [])
        )
        return (f'<svg class="ov" viewBox="0 0 1 1" preserveAspectRatio="none">{rects}</svg>'
                if rects else "")
    sheets_html = "".join(
        f'<div class="sheet" id="sheet-{s["page"]}"><div class="cap">sheet · page {s["page"]} '
        f'· sha256 {s["sha256"][:12]}…</div>'
        f'<div class="imgwrap"><img loading="lazy" alt="drawing sheet page {s["page"]}" '
        f'src="{data_uri(fig_dir / s["file"])}">{_overlay(s["page"])}</div></div>'
        for s in manifest["sheets"]
    )
    def _cap_body(f):                                   # caption text minus the "FIG. N is" lead
        return html.escape(f.description.split(" ", 3)[-1] if f.description else "")
    def _sheet_tag(fig_number: str) -> str:
        a = assignments.get(fig_number)
        if not a:
            return ""
        # The asterisk means "the tool guessed"; a reviewer's confirmation (D87) is the
        # opposite of a guess, so it carries their name instead.
        how = {OCR: f"OCR conf {a.confidence}", HUMAN: f"confirmed by {a.by} on {a.on}"
               }.get(a.method, "by elimination")
        return (f' <span class="sh" data-page="{a.page}" title="{how}">'
                f"sheet p.{a.page}{'*' if a.method == ELIMINATION else ''}</span>")
    def _page_of(fig_number: str) -> str:
        a = assignments.get(fig_number)
        return str(a.page) if a else ""
    figs_html = "".join(
        f'<div class="fig" data-fig="{f.number}" data-page="{_page_of(f.number)}">'
        f'<span class="fl">{f.label}</span>{_sheet_tag(f.number)}'
        f'<div class="fd">{_cap_body(f)}</div></div>'
        for f in figs
    )
    # Acronym reference labels ("STM") get legend chips too — their sightings and
    # confirmation boxes already exist in the manifest; without a chip they would be
    # unreachable in the UI. Only acronyms actually SIGHTED on a sheet get a chip
    # (a prose-only candidate like "PVC" would be noise).
    for a in acronym_labels(text) + dimension_labels(text):
        m = re.search(rf"\b{re.escape(a)}\b", text)
        if m and a in sightings_by_num:
            kind = "dimension callout" if a[0].isalpha() and a[1:].isdigit() else "text label"
            nums = list(nums) + [Numeral(a, f"({kind} on drawing)", m.start(), m.end())]

    # View-marker letters (A/B/C from FIGS. 3A-3C): a sighted letter gets a chip
    # tagged to its sub-figure; an UNLOCATED one is surfaced in the review list —
    # a reviewer saw "A" on FIG 2, so an OCR blind spot must stay visible, never
    # silently absent.
    markers = view_marker_letters(known)
    unlocated_markers = []
    for mk in markers:
        fam = next((f for f in known if f.endswith(mk) and len(f) > 1), "?")
        parent = sub_figure_parent(text, fam[:-1], refs) if fam != "?" else None
        on = f"on FIG. {parent}" if parent else "(no predicted location)"
        if mk in sightings_by_num:
            nums = list(nums) + [Numeral(
                mk, f"(view marker {on} — the FIG. {fam} view direction)", 0, 0)]
        else:
            unlocated_markers.append(
                f"{mk} — expected {on}, marks the FIG. {fam} view direction")

    ctx_json, nums_html = {}, []
    for n in nums:
        first = numeral_figure(n.char_start, refs)          # nearest text FIG (default)
        allf = all_figs_by_num.get(n.number, [])            # every figure OCR located it in
        ctx_json[str(n.number)] = (
            html.escape(f"{n.number}: {n.element}") if n.char_start == n.char_end == 0
            else snippet(text, n.char_start, n.char_end))
        fg_first = (f'<span class="fg only-first">FIG. {first}'
                    f'</span>') if first else ""
        fg_all = (f'<span class="fg only-all">FIGS. {", ".join(allf)}</span>' if allf
                  else ((f'<span class="fg only-all">FIG. {first}</span>' if first else "")
                        if not is_locatable(str(n.number))   # text figure, not OCR
                        else '<span class="fg only-all mut">not located on a sheet</span>'))
        page_method: dict[int, str] = {}
        for s in sightings_by_num.get(n.number, []):
            prev = page_method.get(s.page)
            if prev is None or (prev == "text-guided" and s.method != "text-guided"):
                page_method[s.page] = s.method            # first-pass/human win the label
        def _sh(p: int, n: int = n.number, pm: dict = page_method) -> str:
            kind = pm[p]
            cls, mark, title = "", "", "first-pass OCR"
            if kind == "text-guided":
                cls, mark, title = " tg", "↻ ", "recovered by the text-guided pass"
            elif kind == "human":
                cls, mark = " hu", "👁 "
                title = "human/visually confirmed — OCR cannot read this mark"
            return (f'<span class="sh{cls}" data-page="{p}" data-n="{n}" '
                    f'title="{title}">{mark}p.{p}</span>')
        located = "".join(_sh(p) for p in sorted(page_method))
        if not is_locatable(str(n.number)):
            # D30: recited and named, but deliberately NOT located on the sheets —
            # say so instead of showing an empty or wrong position.
            located = ('<span class="sh to" title="sub-10 numeral: recited in the text '
                       'with its element and figure, but not located on the drawing '
                       '(OCR is unreliable at this size)">text-only</span>')
        nums_html.append(
            f'<span class="num" data-n="{n.number}" data-fig="{first or ""}" '
            f'data-figs="{",".join(allf)}">'
            f'<b>{n.number}</b> {html.escape(n.element)}{fg_first}{fg_all}{located}</span>'
        )
    issues_html, banner = "", ""
    if cov is not None:
        def _nlist(nums_list):
            return ", ".join(str(n) for n in nums_list) or "none"
        _res = [mm for mm in cov.likely_misreads if not mm.get("unresolved")]
        _unr = [mm for mm in cov.likely_misreads if mm.get("unresolved")]
        flags = (len(_unr) + len(cov.recited_not_drawn) + len(cov.drawn_not_recited)
                 + len(cov.figure_mismatches) + len(unlocated_markers))
        mism = "".join(f'<li>{html.escape(m["message"])}</li>' for m in cov.figure_mismatches)
        n_recovered = sum(1 for ss in sightings_by_num.values()
                          for s in ss if s.method == "text-guided")
        recovered_line = (
            f'<li><b style="color:var(--fig)">↻ Text-guided recovery ({n_recovered}):</b> '
            f'where the spec predicted a numeral on a figure\'s sheet but the first OCR pass '
            f'missed it, a tiled re-OCR searched that sheet for exactly that numeral and '
            f'recovered {n_recovered} (marked <span class="sh tg">↻ p.N</span> above). '
            f'The prediction pushes the truth from both angles — text and image.</li>'
            if n_recovered else "")
        # --- the caveat leads, and the discrepancies lead with it -------------------
        # Julian's framing: "for the sake of honoring this tool's entire premise."
        # A tool whose whole claim is ground-or-abstain cannot bury the one step that
        # is neither — so the OCR caveat and the discrepancy tally sit ABOVE the
        # evidence, not under it. Precision matters more than alarm here: OCR is
        # frozen at ingestion, so everything DOWNSTREAM is byte-reproducible (I6);
        # what is not reproducible is the reading itself across engines/versions.
        # Saying "OCR is nondeterministic" flat would be the easier line and the
        # wrong one — it would understate the determinism we do have and overstate
        # the run-to-run variance we do not.
        def _cell(n, label, anchor):
            cls = "zero" if not n else ""
            return (f'<li class="{cls}"><a href="#{anchor}" style="text-decoration:none;'
                    f'color:inherit"><b>{n}</b> {label}</a></li>')

        banner = (
            '<div class="alarm" role="alert">'
            '<h2>⚠ Numeral locations on this page are OCR-derived — the weakest link</h2>'
            'Every box drawn on a drawing is a <b>machine reading of pixels</b>, not a '
            'transcription guarantee and not a citation. This is the one step in CAIRN '
            'that is neither grounded nor abstained: it is <i>judged</i>. Treat it as a '
            'reviewer&rsquo;s aid to be confirmed by eye, never as a settled fact.'
            '<ul class="tally">'
            f'{_cell(len(cov.recited_not_drawn), "recited, not located", "issues")}'
            f'{_cell(len(cov.drawn_not_recited), "located, not recited", "issues")}'
            f'{_cell(len(cov.figure_mismatches), "figure mismatches", "issues")}'
            f'{_cell(len(_unr), "engine disagreements unresolved", "issues")}'
            f'{_cell(len(unlocated_markers), "markers not located", "issues")}</ul>'
            '<p class="fine"><b>What is and is not reproducible.</b> The reading is '
            'frozen into a hashed manifest at ingestion, so everything downstream of it '
            'is byte-identical on every run (I6) and the sheets are never re-OCR&rsquo;d '
            'at answer time. The <i>reading itself</i> carries no such guarantee: a '
            'different engine version, OS, or machine can resolve the same pixels '
            'differently, so re-ingesting elsewhere may not reproduce these boxes. '
            'Three engines are run and cross-checked precisely because each is fallible '
            '&mdash; but they share blind spots, and agreement is corroboration, not proof.'
            '<br><b>Absence of a flag is not evidence of correctness.</b> The checks below '
            'compare the drawings against the specification, so a numeral that OCR missed '
            '<i>and</i> the spec never recites is invisible to every check on this page. '
            'The counts above are a floor on the discrepancies, not a ceiling.</p></div>'
        )

        issues_html = (
            f'<h2 id="issues" style="margin-top:20px">Numeral coverage &amp; consistency '
            f'({flags} flags)</h2>'
            f'<ul class="pe2">'
            f'{recovered_line}'
            + ("".join(f'<li><b>View marker not located:</b> {html.escape(u)} '
                       f'<span class="mut">— OCR could not read it on any sheet; if it is '
                       f'visibly drawn, this is a known OCR blind spot; review.</span></li>'
                       for u in unlocated_markers))
            + ((f'<li><b style="color:var(--fig)">Likely misreads resolved ({len(_res)}):</b> '
                + "; ".join(html.escape(mm["message"]) for mm in _res)
                + "</li>") if _res else "")
            + ((f'<li><b style="color:#f85149">Engine disagreements NOT resolved '
                f'({len(_unr)}):</b> '
                + "; ".join(html.escape(mm["message"]) for mm in _unr)
                + "</li>") if _unr else "")
            + f'<li><b>Recited in the spec but not found on any drawing '
            f'({len(cov.recited_not_drawn)}):</b> {_nlist(cov.recited_not_drawn)} '
            f'<span class="mut">— OCR miss, or the number is not drawn; review.</span></li>'
            f'<li><b>Found on a drawing but not recited in the spec '
            f'({len(cov.drawn_not_recited)}):</b> {_nlist(cov.drawn_not_recited)} '
            f'<span class="mut">— an OCR artefact, or an unlabelled element; review.</span></li>'
            f'<li><b>Discussed with a figure but not located on that sheet '
            f'({len(cov.figure_mismatches)}):</b><ul class="pe2">{mism}</ul></li>'
            f'<li class="mut">Consecutive-number check: the figure-tied reference numerals run '
            f'{cov.figure_tied[0] if cov.figure_tied else "?"}–'
            f'{cov.figure_tied[-1] if cov.figure_tied else "?"} and are '
            f'<b>non-contiguous by design</b> (patents skip reference numerals), so a raw list '
            f'of missing integers is a weak signal, not shown as a flag — the three checks above '
            f'are the reliable OCR-miss / document-gap detectors.</li>'
            f'</ul>')
    note = (
        "Drawings are <i>displayed evidence</i>, not text citations (truth-contract D21): "
        "grounding binds a claim to the text that recites a numeral; the sheet rides alongside. "
        "The <b>show: first discussed / all figures</b> toggle switches a numeral's tag between "
        "its nearest text mention and <i>every</i> figure OCR located it in (a shared component "
        "appears in several). Click a numeral to draw a <b>confirmation box</b> around it on its "
        "sheet(s); a <b>p.N</b> tag jumps to that sheet. All OCR-located (D28 — ingestion-time, "
        "manifest, confidence-carrying, not 100% reliable; * = figure assigned by elimination). "
        "Locate-only aids (D10) — never claims about what a figure depicts. The structural-review "
        "list surfaces facts for a professional; it draws no §112 conclusions."
    )
    page = PAGE.format(
        title=f"{ns.doc} — drawings", h1=f"{ns.doc} · drawings",
        sub=f"{len(manifest['sheets'])} sheets · {len(figs)} figures · "
            f"{len(nums)} reference numerals",
        nsheets=len(manifest["sheets"]), nfigs=len(figs), nnums=len(nums),
        sheets=sheets_html, figs=figs_html, nums="".join(nums_html), issues=issues_html,
        banner=banner,
        ctx_json=json.dumps(ctx_json), note=note,
    )
    Path(ns.out).write_text(page, encoding="utf-8")
    print(f"OK — wrote {ns.out} ({len(manifest['sheets'])} sheets, {len(figs)} figures, "
          f"{len(nums)} numerals) from {ns.doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
