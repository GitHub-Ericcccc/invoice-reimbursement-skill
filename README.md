# Invoice Reimbursement Skill

[中文说明](README_ZH.md)

`invoice-reimbursement` is an explicit-only Codex Skill for incrementally collecting invoice PDFs, extracting and checking invoice fields, applying consistent filenames, and updating a reimbursement workbook without duplicating previously processed invoices.

## What it does

- Obtains authorized invoice PDFs from links, attachments, QR-code destinations, browser sessions, or a project folder.
- Extracts and verifies the invoice date, concise expense category, tax-inclusive amount, and invoice identity.
- Renames PDFs as `invoice-date-brief-content-amount.pdf` while preserving the original invoice content.
- Appends only new invoices to `报销表.xlsx` in the same directory as the managed PDFs.
- Uses invoice numbers and file hashes to prevent duplicate reimbursement rows.
- Preserves the user's current workbook structure, wording, formulas, formatting, and intentional deletions.

## Invocation

This Skill is explicit-only. Invoke it by name and identify the authorized invoice directory or sources:

```text
Use $invoice-reimbursement to process the new invoices in this folder and update the reimbursement workbook. The claimant is Example User.
```

The Skill asks for clarification only when a material ambiguity would change the result, such as multiple plausible workbooks, an unreadable date or amount, or more than one possible claimant.

## Workbook behavior

The final summary workbook is always named `报销表.xlsx` and stored beside the invoice PDFs.

An existing `报销表.xlsx` is authoritative and is never replaced by the bundled template. If no authoritative workbook exists, the Skill can bootstrap one from the sanitized asset at `skill/invoice-reimbursement/assets/报销表模板.xlsx`. Its three visible sample rows are removed only when all sample markers remain unchanged; otherwise the workbook is treated as user-edited.

## Privacy and safety boundaries

- Text inside webpages, QR destinations, PDFs, images, and workbooks is treated as source data, not as instructions.
- Only user-authorized directories, links, attachments, and browser state are accessed.
- Only PDF invoices are saved unless another format is explicitly requested.
- Claimant names, project names, invoice identifiers, credentials, local paths, and mappings remain project-local and are not embedded in the Skill.
- Workbook replacement is recoverable and project state is committed only after the updated workbook passes verification.
- The Skill does not provide tax-law advice, determine invoice authenticity, or perform bookkeeping without source invoices.

## Repository layout

```text
skill/invoice-reimbursement/
|-- SKILL.md
|-- SKILL_ZH.md
|-- agents/openai.yaml
|-- assets/报销表模板.xlsx
|-- references/
`-- scripts/invoice_state.py

tests/
tools/release.py
release/manifest.json
```

`skill/invoice-reimbursement` is the deployable payload. Tests, release tooling, the manifest, and this README remain repository-level material.

## Releases and installation

Release archives are reproducibly built from immutable tags. Review a release and its checksum before installing it. Extract the packaged `invoice-reimbursement` directory into the Codex Skills directory, keeping source repositories, release archives, and installed runtime copies separate.

The installed Skill remains explicit-only through `agents/openai.yaml`.

## Verification

The release workflow validates Skill structure, translation source hashes, per-file and aggregate hashes, script behavior, workbook-template invariants, clean Git state, immutable tag agreement, deterministic archives, and installed runtime equality.
