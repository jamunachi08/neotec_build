# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

"""Shared billing math and settings resolution for NeoBuild.

All monetary/progress logic lives here (versioned module, not Server
Scripts) so RA Bills and IPCs share one implementation.
"""

import frappe
from frappe import _
from frappe.utils import flt

PRECISION = 2
QTY_PRECISION = 4


def get_settings():
	return frappe.get_cached_doc("NeoBuild Settings")


def get_company_defaults(company):
	"""Return the NeoBuild Company Defaults row for a company (or empty dict)."""
	settings = get_settings()
	for row in settings.get("company_defaults") or []:
		if row.company == company:
			return row
	return frappe._dict()


def resolve_default(project, project_field, settings_field):
	"""Resolution order: Project override → NeoBuild Settings global default.

	Document-level values always win over both; controllers only call this
	when the document field is empty/zero.
	"""
	if project:
		value = flt(frappe.db.get_value("Project", project, project_field))
		if value:
			return value
	return flt(get_settings().get(settings_field))


def get_subcontract_retention_percent(project):
	return resolve_default(project, "neotec_retention_percent", "default_retention_percent")


def get_advance_recovery_percent(project):
	return resolve_default(
		project, "neotec_advance_recovery_percent", "default_advance_recovery_percent"
	)


def get_client_retention_percent(project):
	return resolve_default(
		project, "neotec_client_retention_percent", "default_retention_percent"
	)


def require_company_account(company, fieldname, label):
	row = get_company_defaults(company)
	account = row.get(fieldname)
	if not account:
		frappe.throw(
			_("Please set {0} for company {1} in NeoBuild Settings → Company Defaults.").format(
				label, frappe.bold(company)
			)
		)
	return account


def compute_current_rows(items, qty_field="cumulative_qty", prev_field="prev_cumulative_qty",
		limit_field=None, limit_label=None):
	"""Compute this-bill qty/amount per row from cumulative measurements.

	Enforces: prev <= cumulative <= limit (when a limit field is given).
	Returns the gross amount for the bill.
	"""
	gross = 0.0
	for row in items:
		cumulative = flt(row.get(qty_field), QTY_PRECISION)
		prev = flt(row.get(prev_field), QTY_PRECISION)

		if cumulative < prev:
			frappe.throw(
				_("Row #{0}: Cumulative qty ({1}) cannot be less than previously billed qty ({2}).").format(
					row.idx, cumulative, prev
				)
			)

		if limit_field:
			limit = flt(row.get(limit_field), QTY_PRECISION)
			if limit and cumulative > limit:
				frappe.throw(
					_("Row #{0}: Cumulative qty ({1}) exceeds {2} ({3}). Issue a variation/amendment first.").format(
						row.idx, cumulative, limit_label or limit_field, limit
					)
				)

		current_qty = flt(cumulative - prev, QTY_PRECISION)
		amount = flt(current_qty * flt(row.rate), PRECISION)
		row.current_qty = current_qty
		row.amount = amount
		gross += amount

	return flt(gross, PRECISION)


def compute_deductions(gross, retention_percent, advance_recovery_percent=0,
		advance_outstanding=0, other_deductions=0):
	"""Return (retention_amount, advance_recovery_amount, net)."""
	retention = flt(gross * flt(retention_percent) / 100.0, PRECISION)

	advance_recovery = flt(gross * flt(advance_recovery_percent) / 100.0, PRECISION)
	advance_outstanding = flt(advance_outstanding, PRECISION)
	if advance_recovery > advance_outstanding:
		advance_recovery = advance_outstanding

	net = flt(gross - retention - advance_recovery - flt(other_deductions), PRECISION)
	if net < 0:
		frappe.throw(_("Net payable cannot be negative. Review deductions."))
	return retention, advance_recovery, net


def validate_retention_percent(retention_percent):
	settings = get_settings()
	max_pct = flt(settings.max_retention_percent)
	if max_pct and flt(retention_percent) > max_pct:
		frappe.throw(
			_("Retention % ({0}) exceeds the maximum allowed ({1}%) set in NeoBuild Settings.").format(
				retention_percent, max_pct
			)
		)


def get_retention_held(party_type, party, company, work_order=None, boq=None):
	"""Net retention currently held for a party = withheld - released."""
	if party_type == "Supplier":
		filters = {"docstatus": 1, "supplier": party, "company": company}
		if work_order:
			filters["work_order"] = work_order
		withheld = frappe.get_all(
			"RA Bill", filters=filters, fields=["sum(retention_amount) as total"]
		)[0].total or 0
	else:
		filters = {"docstatus": 1, "customer": party, "company": company}
		if boq:
			filters["boq"] = boq
		withheld = frappe.get_all(
			"Interim Payment Certificate",
			filters=filters,
			fields=["sum(retention_amount) as total"],
		)[0].total or 0

	release_filters = {
		"docstatus": 1,
		"party_type": party_type,
		"party": party,
		"company": company,
	}
	if work_order:
		release_filters["work_order"] = work_order
	if boq:
		release_filters["boq"] = boq
	released = frappe.get_all(
		"Retention Release", filters=release_filters, fields=["sum(amount) as total"]
	)[0].total or 0

	return flt(withheld) - flt(released)
