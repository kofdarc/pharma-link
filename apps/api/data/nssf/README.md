# NSSF reimbursable-drug lists

Source: **National Social Security Fund / CNSS** — <https://www.cnss.gov.lb/> →
"لوائح الأدوية المعدّلة وفق التعرفات الجديدة" (revised medicine lists per the new
tariffs). The site links the files as Google Drive PDFs.

| File | Coverage tier | Drive id |
|---|---|---|
| `nssf_list_80pct_2025-04.pdf` | Standard, 80% | `16HL_ZnuMvSFb0PEUNIHC-IL_FRnTimX1` |
| `nssf_list_95pct_2025-04.pdf` | Chronic / incurable, 95% (some 90%) | `1LIqG2wkQ_tLJMq5uWzoz-EJtK2f7adB7` |

Both are dated **2025/4/17** and were re-priced off MoPH's 4 Mar 2025 price index. The
95% file is a **superset** of the 80% file (it repeats every 80% row and adds the 95%
ones).

Re-download:

```
curl -sSL "https://drive.google.com/uc?export=download&id=<id>" -o <file>.pdf
```

## Importing

```
python manage.py import_nssf_coverage \
    --file apps/api/data/nssf/nssf_list_80pct_2025-04.pdf \
    --file apps/api/data/nssf/nssf_list_95pct_2025-04.pdf
```

- Needs `pdftotext` (poppler) on PATH; or pass a pre-extracted `.txt`.
- Matches rows to `Medicine.moph_code` (the list's `Code` column). ~86% of list codes
  have a catalog entry; the rest are reported and skipped.
- List prices are LBP; `--lbp-per-usd` (default 89500, the BdL peg) converts them to the
  USD unit the catalog stores prices in. The divisor is recorded in
  `nssf_source_reference`.
- Idempotent. Coverage set by a previous run is cleared for medicines no longer on the
  lists; manually entered coverage (a different `nssf_source_reference`) is left alone.

## When the NSSF publishes a new revision

1. Download the two new PDFs, name them `nssf_list_{80,95}pct_YYYY-MM.pdf`.
2. `python manage.py import_nssf_coverage --file ...80... --file ...95... --list-date YYYY-MM-DD`
3. Check the `--lbp-per-usd` peg is still current.
