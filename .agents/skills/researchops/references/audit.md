# Audit mode

Use after substantive scientific revisions are stable, not after every paragraph.
The audit is read-only with respect to the manuscript.

```bash
PYTHONPATH=ResearchOps/src python3 -m researchops audit ARTICLE MANUSCRIPT \
  --journal-config ACADEMIC_PUBLICATION_QA/configs/JOURNAL.json \
  --compare-root FINAL_ARTICLES_TO_SUBMIT
```

Interpret `BLOCKER`, `IMPORTANT`, and `MINOR` as review candidates requiring human
adjudication. Do not present the result as an acceptance probability or an AI
authorship detector. After changes to model, data, results, or central claims,
rerun the scientific checks before style polishing.
