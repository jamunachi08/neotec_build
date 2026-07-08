# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from neotec_build.utils import billing


class SubcontractWorkOrder(Document):
	def validate(self):
		self.validate_boq()
		self.apply_defaults()
		billing.validate_retention_percent(self.retention_percent)
		self.validate_items_against_boq()
		self.compute_totals()
		self.set_status()

	def validate_boq(self):
		boq_status, boq_project = frappe.db.get_value("BOQ", self.boq, ["status", "project"])
		if boq_status not in ("Active",):
			frappe.throw(_("BOQ {0} must be submitted and Active.").format(self.boq))
		if self.project and boq_project != self.project:
			frappe.throw(_("BOQ {0} belongs to a different Project.").format(self.boq))

	def apply_defaults(self):
		# Resolution: this document → Project override → NeoBuild Settings
		if self.retention_percent is None or self.retention_percent == 0:
			self.retention_percent = billing.get_subcontract_retention_percent(self.project)
		if self.advance_amount and not self.advance_recovery_percent:
			self.advance_recovery_percent = billing.get_advance_recovery_percent(self.project)

	def validate_items_against_boq(self):
		"""WO qty per BOQ line (across all submitted WOs) must not exceed BOQ qty."""
		boq_items = {
			row.name: row
			for row in frappe.get_all(
				"BOQ Item",
				filters={"parent": self.boq},
				fields=["name", "qty", "uom", "description", "item_code"],
			)
		}
		for row in self.items:
			if not row.boq_item_row:
				continue
			boq_row = boq_items.get(row.boq_item_row)
			if not boq_row:
				frappe.throw(_("Row #{0}: BOQ item reference not found in BOQ {1}.").format(row.idx, self.boq))

			already = flt(
				frappe.db.sql(
					"""
					select coalesce(sum(swi.qty), 0)
					from `tabSubcontract Work Order Item` swi
					join `tabSubcontract Work Order` swo on swo.name = swi.parent
					where swi.boq_item_row = %s and swo.docstatus = 1 and swo.name != %s
					""",
					(row.boq_item_row, self.name or "New"),
				)[0][0]
			)
			if flt(already) + flt(row.qty) > flt(boq_row.qty):
				frappe.throw(
					_(
						"Row #{0}: total subcontracted qty ({1}) would exceed BOQ qty ({2}) for item '{3}'."
					).format(row.idx, flt(already) + flt(row.qty), boq_row.qty, boq_row.description[:60])
				)

	def compute_totals(self):
		total = 0.0
		for row in self.items:
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			total += row.amount
		self.total_amount = flt(total, 2)
		if flt(self.advance_amount) > self.total_amount:
			frappe.throw(_("Mobilization advance cannot exceed the WO value."))

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 2:
			self.status = "Cancelled"
		elif self.docstatus == 1 and self.status in ("Draft", "", None):
			self.status = "In Progress"

	def on_submit(self):
		self.db_set("status", "In Progress")
		self._update_boq_tracking()

	def on_cancel(self):
		if frappe.db.exists("RA Bill", {"work_order": self.name, "docstatus": 1}):
			frappe.throw(_("Cannot cancel: submitted RA Bills exist against this Work Order."))
		self.db_set("status", "Cancelled")
		self._update_boq_tracking()

	def _update_boq_tracking(self):
		from neotec_build.neotec_build.doctype.boq.boq import update_boq_item_tracking

		update_boq_item_tracking(self.boq)

	def update_billing_status(self):
		"""Refresh cumulative billed/retention/advance figures from submitted RA Bills."""
		totals = frappe.get_all(
			"RA Bill",
			filters={"work_order": self.name, "docstatus": 1},
			fields=[
				"sum(gross_amount) as gross",
				"sum(retention_amount) as retention",
				"sum(advance_recovery_amount) as advance",
			],
		)[0]
		self.db_set(
			{
				"total_billed_amount": flt(totals.gross),
				"total_retention_held": flt(totals.retention),
				"advance_recovered": flt(totals.advance),
			},
			update_modified=False,
		)

		fully_billed = flt(totals.gross) >= flt(self.total_amount) and flt(self.total_amount) > 0
		if self.docstatus == 1:
			self.db_set("status", "Completed" if fully_billed else "In Progress", update_modified=False)

		# refresh per-row billed qty
		billed = {}
		for bill in frappe.get_all("RA Bill", filters={"work_order": self.name, "docstatus": 1}, pluck="name"):
			for row in frappe.get_all(
				"RA Bill Item", filters={"parent": bill}, fields=["wo_item_row", "current_qty"]
			):
				if row.wo_item_row:
					billed[row.wo_item_row] = billed.get(row.wo_item_row, 0) + flt(row.current_qty)
		for item in self.items:
			frappe.db.set_value(
				"Subcontract Work Order Item",
				item.name,
				"billed_qty",
				flt(billed.get(item.name, 0), 4),
				update_modified=False,
			)


@frappe.whitelist()
def make_work_order_from_boq(boq, supplier=None):
	"""Map an Active BOQ into a draft Subcontract Work Order (full remaining scope)."""
	frappe.has_permission("Subcontract Work Order", "create", throw=True)
	boq_doc = frappe.get_doc("BOQ", boq)
	if boq_doc.status != "Active":
		frappe.throw(_("BOQ must be Active."))

	wo = frappe.new_doc("Subcontract Work Order")
	wo.update(
		{
			"wo_title": _("SWO for {0}").format(boq_doc.boq_title),
			"boq": boq_doc.name,
			"project": boq_doc.project,
			"company": boq_doc.company,
			"supplier": supplier,
		}
	)
	for row in boq_doc.items:
		remaining = flt(row.qty) - flt(row.subcontracted_qty)
		if remaining <= 0:
			continue
		wo.append(
			"items",
			{
				"boq_item_row": row.name,
				"item_code": row.item_code,
				"description": row.description,
				"uom": row.uom,
				"qty": remaining,
				"rate": row.rate,
			},
		)
	if not wo.items:
		frappe.throw(_("No remaining BOQ quantity available to subcontract."))
	return wo.as_dict()
