#!/usr/bin/env python3
"""Build the signable record of inquiry from the audit log (RT-5).

The deliverable a professional can actually buy: not the answer, but the documented
inquiry — what was searched (with hashes), what each question resolved to, what was cited
at which offsets, what was surfaced and set aside, and under exactly what declared limits.

    python scripts/build_review_report.py --store corpus/store \\
        --audit audit_log/agent.jsonl --on 2026-07-28 --out record.html

`--on` is required and supplied by hand: cores never read the clock, so a report is
reproducible from the same log (I6).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401  (puts src/ on sys.path)

from cairn import claim_record
from cairn.audit import AuditLog
from cairn.evidence_view import interactions_from_audit
from cairn.ingest import DocumentStore
from cairn.review_report import ReportData, corpus_identity, render
from cairn.spans import SpanStore


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the signable record of inquiry (RT-5)")
    ap.add_argument("--store", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--on", required=True, metavar="YYYY-MM-DD",
                    help="generation date (supplied, never read from the clock — I6)")
    ap.add_argument("--engagement", default=None, help="engagement label for the header")
    ap.add_argument("--doc", default=None,
                    help="patent document id — adds the claims section (D89)")
    ap.add_argument("--out", default="record_of_inquiry.html")
    ns = ap.parse_args()

    doc_store = DocumentStore(ns.store)
    span_store = SpanStore.from_store(doc_store)
    entries = [e.payload for e in AuditLog(ns.audit).entries()]
    interactions = interactions_from_audit(entries, span_store)

    # Built from the hash-verified text, so every offset in the section resolves
    # against the document whose hash the record publishes (I1/I3).
    claims = (claim_record.build(ns.doc, span_store.get_document(ns.doc))
              if ns.doc else None)

    data = ReportData(
        engagement=ns.engagement or Path(ns.store).parent.name,
        corpus=corpus_identity(ns.store, doc_store),
        interactions=interactions, entries=entries, generated_on=ns.on,
        claims=claims)

    Path(ns.out).write_text(render(data), encoding="utf-8")
    counts: dict[str, int] = {}
    for i in interactions:
        counts[i.kind] = counts.get(i.kind, 0) + 1
    print(f"OK — wrote {ns.out}")
    print(f"  corpus      : {len(data.corpus.doc_ids)} document(s), "
          f"{'calibrated' if data.corpus.calibrated else 'NOT CALIBRATED'}")
    print(f"  interactions: {len(interactions)}  {counts or '(none)'}")
    if claims is not None:
        print(f"  claims      : {len(claims.claims)} claims, {claims.n_limitations} "
              f"limitations, {claims.limitations_with_absent_words} using a word the "
              f"description never does")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
