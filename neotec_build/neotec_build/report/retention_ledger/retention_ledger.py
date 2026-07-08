# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 100},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
		{"label": _("Project"), "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 160},
		{"label": _("Reference"), "fieldname": "reference", "fieldtype": "Data", "width": 180},
		{"label": _("Retention Withheld"), "fieldname": "withheld", "fieldtype": "Currency", "width": 150},
		{"label": _("Released"), "fieldname": "released", "fieldtype": "Currency", "width": 130},
		{"label": _("Held (Net)"), "fieldname": "held", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("project"):
		conditions["project"] = filters.project

	rows = []

	# Subcontractor retention — grouped by Work Order
	wo_bills = frappe.get_all(
		"RA Bill",
		filters=conditions,
		fields=["supplier", "project", "work_order", "sum(retention_amount) as withheld"],
		group_by="work_order",
	)
	for b in wo_bills:
		released = flt(
			frappe.get_all(
				"Retention Release",
				filters={"docstatus": 1, "party_type": "Supplier", "party": b.supplier, "work_order": b.work_order},
				fields=["sum(amount) as total"],
			)[0].total
		)
		rows.append(
			{
				"party_type": "Supplier",
				"party": b.supplier,
				"project": b.project,
				"reference": b.work_order,
				"withheld": flt(b.withheld),
				"released": released,
				"held": flt(b.withheld) - released,
			}
		)

	# Client retention — grouped by BOQ
	ipc_conditions = dict(conditions)
	ipcs = frappe.get_all(
		"Interim Payment Certificate",
		filters=ipc_conditions,
		fields=["customer", "project", "boq", "sum(retention_amount) as withheld"],
		group_by="boq",
	)
	for c in ipcs:
		released = flt(
			frappe.get_all(
				"Retention Release",
				filters={"docstatus": 1, "party_type": "Customer", "party": c.customer, "boq": c.boq},
				fields=["sum(amount) as total"],
			)[0].total
		)
		rows.append(
			{
				"party_type": "Customer",
				"party": c.customer,
				"project": c.project,
				"reference": c.boq,
				"withheld": flt(c.withheld),
				"released": released,
				"held": flt(c.withheld) - released,
			}
		)

	return rows
