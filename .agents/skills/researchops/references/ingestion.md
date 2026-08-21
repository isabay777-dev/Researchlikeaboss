# Document ingestion

Read this only when a complex local source must be converted.

1. Initialize the article directory if `.researchops/config.json` is absent.
2. Extract only the source needed for the current claim or section.
3. For Markdown/TXT/CSV, use the base command. PDF/DOCX/XLSX requires the
   optional Docling extra.
4. Keep the default one-job lock, 80 MB limit, and 300-second timeout unless the
   user knowingly changes them.
5. Do not automatically retry a timeout. Report the file and stop reason.
6. Use the stored SHA-256 metadata to link excerpts back to the original.

```bash
PYTHONPATH=ResearchOps/src python3 -m researchops extract ARTICLE SOURCE
```
