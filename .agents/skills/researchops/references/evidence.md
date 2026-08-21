# Evidence mode

Use this mode when a paragraph, claim, novelty statement, or reviewer response
needs support from already extracted local sources.

Build a narrow query around the exact construct, mechanism, population, method,
or result. Generate a bounded pack:

```bash
PYTHONPATH=ResearchOps/src python3 -m researchops pack ARTICLE \
  --query "specific mechanism or claim"
```

Read `ARTICLE/.researchops/EVIDENCE_PACK.md` first. Open the full extracted source
only to validate context, page/table provenance, or an exact quotation. A high
text-match score is retrieval relevance, not scientific support; adjudicate the
claim against the source.

For source discovery, PyAlex returns candidates and metadata only. Prefer DOI and
primary publication pages for verification.
