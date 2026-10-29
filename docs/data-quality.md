# Data-quality policy

**Terms.** *Source row*: a data line in the CSV. *Stored*: saved in `sales_transactions` (raw row kept as JSON). *Valid*: stored with no issues. *Eligible*: valid **and** Completed **and** quantity > 0 → the only rows used by analytics. *Rejected*: not stored; reason in `data_quality_issues`.

**Eligible revenue** = Σ (quantity × unit_price − discount_amount) over eligible rows.

| Rule | Outcome |
|---|---|
| Blank/duplicate Transaction_Id (2nd occurrence in file) | rejected, issue logged |
| Invalid date (must be real DD-MM-YYYY; stored ISO) | rejected |
| Non-integer or negative quantity | rejected |
| Missing unit price | stored with NULL, flagged `missing_unit_price`, excluded (never converted to 0) |
| Non-numeric / negative price | stored, price NULL, flagged, excluded |
| Blank discount | treated as 0 (documented assumption); negative/non-numeric/greater than gross → flagged, excluded |
| Status Returned | stored, `returned`, excluded |
| Quantity 0 | stored, flagged `zero_quantity`, excluded |
| Unknown status | stored, flagged, excluded |
| Row already in DB (re-import) | skipped as `already_present` |

**Summary categories are mutually exclusive** (priority: rejected → already_present → returned → zero_quantity → missing/invalid price → other_flagged → eligible) so they sum to source rows. Result for the supplied file: 51 = 48 eligible + 1 returned + 1 zero-quantity + 1 missing-price + 0 rejected.

**Audit.** Each import writes `import_runs` (summary JSON) and `data_quality_issues` (row number, id, code, detail, raw row). Import runs in one transaction (all-or-nothing on unexpected errors).
