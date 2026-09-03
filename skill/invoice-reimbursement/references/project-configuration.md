# 项目本地配置

Project-specific values must stay outside the Skill, preferably in `<project>/.codex/invoice-reimbursement-config.json`. Create or change this file only while executing an authorized project task.

Suggested schema:

```json
{
  "schema_version": 1,
  "workbook": "报销表.xlsx",
  "sheet": "reimbursement details",
  "claimant": "project-local claimant",
  "filename_pattern": "YYYY-MM-DD-简要内容-金额.pdf",
  "amount_basis": "tax_inclusive_total",
  "category_mappings": {
    "normalized invoice category": {
      "filename_content": "concise content",
      "workbook_type": "existing workbook wording",
      "workbook_note": "existing workbook wording or null"
    }
  },
  "column_mappings": {
    "sequence": "exact live header",
    "period": "exact live header",
    "type": "exact live header",
    "amount": "exact live header",
    "claimant": "exact live header",
    "note": "exact live header",
    "actual_amount": "exact live header",
    "face_amount": "exact live header"
  }
}
```

Bootstrap mappings from the latest user-edited workbook only when the relationship is clear. Persist explicit corrections so later incremental runs reuse them. Never package the resulting configuration, state, names, invoice numbers, URLs, or paths with the Skill.

`workbook` is fixed to `报销表.xlsx`. It is shown in the schema for clarity but is not configurable. The file must be stored directly beside the managed invoice PDFs.
