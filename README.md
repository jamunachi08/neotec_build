# NeoBuild (`neotec_build`) — v0.1.0

**Construction contracting suite for KSA on Frappe/ERPNext v15**
by Neotec Integrated Solution — support@neotec.ai

Phase 1 scope: **BOQ → Subcontract Work Orders → RA (progress) Billing → Client IPCs → Retention & Advance management**, with automated draft Purchase/Sales Invoices and retention Journal Entries.

> ZATCA e-invoicing is intentionally **out of scope** — install the ERPGulf ZATCA app alongside NeoBuild; it operates on the Sales Invoices NeoBuild generates.

---

## Install

```bash
bench get-app https://github.com/<your-org>/neotec_build.git
bench --site <site> install-app neotec_build
bench --site <site> migrate
```

Roles (`NeoBuild Manager`, `NeoBuild User`), custom fields on Purchase/Sales Invoice, and the **NeoBuild** workspace are created idempotently on install/migrate — no manual fixtures.

## One-time configuration (NeoBuild Settings)

1. Set default/max **Retention %** and default **Advance Recovery %**.
2. Add a **Company Defaults** row per company:
   - Retention Payable Account (liability)
   - Retention Receivable Account (asset)
   - Subcontractor Advance Account (asset)
   - Subcontract Expense Account
   - Subcontract Service Item (non-stock service item)
   - Contract Revenue Item (non-stock service item)
3. Automation toggles: auto-create draft PI / retention JE on RA Bill submit, auto-create draft SI on IPC submit (all ON by default).

## Workflow

```
BOQ (import Excel EN/AR → submit → Active)
 ├─ Create ▸ Subcontract Work Order  (scope capped at remaining BOQ qty)
 │    └─ Create ▸ RA Bill  (cumulative measurement, auto prev-qty,
 │         retention + advance recovery + net payable)
 │         └─ on submit: draft Purchase Invoice (gross)
 │                       + draft JE (Dr Creditors / Cr Retention Payable,
 │                                    Cr Subcontractor Advance)
 │             → net creditor balance = net payable ✔
 ├─ Create ▸ Interim Payment Certificate  (client-side measurement vs BOQ)
 │         └─ on submit: draft Sales Invoice (gross) → ERPGulf ZATCA takes over
 └─ Retention Release (First Moiety 50% / Final / Custom)
           └─ on submit: draft JE releasing retention to Creditors/Debtors
```

**Controls enforced in code (versioned modules, no Server Scripts):**
- Cumulative measured qty can never exceed WO qty (RA Bill) or BOQ qty (IPC), and can never go below previously billed qty.
- Total subcontracted qty per BOQ line across all submitted WOs is capped at the BOQ qty.
- Retention % capped by NeoBuild Settings; net payable can never go negative.
- Advance recovery auto-caps at the outstanding advance.
- Retention Release amount capped at net retention currently held (withheld − released).
- Cancellation is blocked while downstream submitted documents exist.

## BOQ Excel import

Draft BOQ → **Import Items from Excel**. Runs on the `long` queue (background job); you're notified on completion and a comment is logged on the BOQ. Recognised headers (EN/AR, order-independent):

| Field | English | Arabic |
|---|---|---|
| Section | Section, Division | القسم، الباب |
| Item Code | Item Code, Code | رمز البند |
| Description* | Description, Scope | الوصف، البند |
| UOM* | UOM, Unit | الوحدة |
| Qty* | Qty, Quantity | الكمية |
| Rate* | Rate, Price | السعر |

Unknown UOMs are auto-created.

## API (role-guarded, `@frappe.whitelist`)

- `neotec_build.api.import_boq_from_file(boq, file_url)` — enqueue import
- `neotec_build.api.get_project_billing_summary(project)` — BOQ value, certified, committed, billed, retention positions (both directions)

## Reports

- **Retention Ledger** — withheld / released / net held per party per WO/BOQ, filterable by company & project.

## Roadmap

- **Phase 2:** daily site reports, material reconciliation, equipment allocation, S-curves
- **Phase 3:** Muqeem-linked site manpower & Saudization per project (via `alphax_muqeem` / `alphax_hr_shield`), client/consultant portal, Ollama-assisted BOQ classification and invoice-to-BOQ matching
