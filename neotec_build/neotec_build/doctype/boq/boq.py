# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BOQ(Document):
	def validate(self):
		self.set_currency()
		self.compute_totals()
		self.set_status()

	def set_currency(self):
		if not self.currency and self.company:
			self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def compute_totals(self):
		total_qty = 0.0
		total_amount = 0.0
		for row in self.items:
			row.amount = flt(flt(row.qty) * flt(row.rate), 2)
			total_qty += flt(row.qty)
			total_amount += row.amount
		self.total_qty = flt(total_qty, 4)
		self.total_amount = flt(total_amount, 2)

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 1:
			self.status = self.status if self.status in ("Active", "Closed") else "Active"
		elif self.docstatus == 2:
			self.status = "Cancelled"

	def on_submit(self):
		self.db_set("status", "Active")

	def on_cancel(self):
		self.validate_no_linked_documents()
		self.db_set("status", "Cancelled")

	def validate_no_linked_documents(self):
		for doctype, field in (
			("Subcontract Work Order", "boq"),
			("Interim Payment Certificate", "boq"),
		):
			if frappe.db.exists(doctype, {field: self.name, "docstatus": 1}):
				frappe.throw(
					_("Cannot cancel: submitted {0} documents exist against this BOQ.").format(doctype)
				)

	@frappe.whitelist()
	def close_boq(self):
		if self.docstatus != 1:
			frappe.throw(_("Only submitted BOQs can be closed."))
		self.db_set("status", "Closed")
		return self.status


def update_boq_item_tracking(boq_name):
	"""Recompute subcontracted_qty and billed_qty on BOQ Items from
	submitted Work Orders and IPCs. Idempotent; safe to call repeatedly."""
	boq = frappe.get_doc("BOQ", boq_name)

	sub_map = {}
	for wo in frappe.get_all(
		"Subcontract Work Order", filters={"boq": boq_name, "docstatus": 1}, pluck="name"
	):
		for row in frappe.get_all(
			"Subcontract Work Order Item",
			filters={"parent": wo},
			fields=["boq_item_row", "qty"],
		):
			if row.boq_item_row:
				sub_map[row.boq_item_row] = sub_map.get(row.boq_item_row, 0) + flt(row.qty)

	billed_map = {}
	for ipc in frappe.get_all(
		"Interim Payment Certificate", filters={"boq": boq_name, "docstatus": 1}, pluck="name"
	):
		for row in frappe.get_all(
			"IPC Item",
			filters={"parent": ipc},
			fields=["boq_item_row", "current_qty"],
		):
			if row.boq_item_row:
				billed_map[row.boq_item_row] = billed_map.get(row.boq_item_row, 0) + flt(row.current_qty)

	for item in boq.items:
		frappe.db.set_value(
			"BOQ Item",
			item.name,
			{
				"subcontracted_qty": flt(sub_map.get(item.name, 0), 4),
				"billed_qty": flt(billed_map.get(item.name, 0), 4),
			},
			update_modified=False,
		)
