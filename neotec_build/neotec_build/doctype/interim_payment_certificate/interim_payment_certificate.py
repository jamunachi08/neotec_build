# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from neotec_build.utils import billing


class InterimPaymentCertificate(Document):
	def validate(self):
		self.validate_boq()
		self.set_ipc_number()
		self.apply_defaults()
		billing.validate_retention_percent(self.retention_percent)
		self.load_previous_cumulative()
		self.compute_amounts()
		self.set_title()
		self.set_status()

	def validate_boq(self):
		status = frappe.db.get_value("BOQ", self.boq, "status")
		if status != "Active":
			frappe.throw(_("BOQ {0} must be Active to certify progress.").format(self.boq))
		if not frappe.db.get_value("BOQ", self.boq, "customer"):
			frappe.throw(_("BOQ {0} has no Customer set.").format(self.boq))

	def set_ipc_number(self):
		if not self.ipc_number:
			last = frappe.db.get_value(
				"Interim Payment Certificate",
				{"boq": self.boq, "docstatus": 1},
				"max(ipc_number)",
			)
			self.ipc_number = (last or 0) + 1

	def apply_defaults(self):
		# Resolution: this document → Project override → NeoBuild Settings
		if self.retention_percent is None or self.retention_percent == 0:
			self.retention_percent = billing.get_client_retention_percent(self.project)

	def load_previous_cumulative(self):
		prev = {}
		for ipc in frappe.get_all(
			"Interim Payment Certificate",
			filters={"boq": self.boq, "docstatus": 1, "name": ("!=", self.name or "New")},
			pluck="name",
		):
			for row in frappe.get_all(
				"IPC Item", filters={"parent": ipc}, fields=["boq_item_row", "current_qty"]
			):
				if row.boq_item_row:
					prev[row.boq_item_row] = prev.get(row.boq_item_row, 0) + flt(row.current_qty)

		boq_items = {
			row.name: row
			for row in frappe.get_all(
				"BOQ Item",
				filters={"parent": self.boq},
				fields=["name", "qty", "rate", "uom", "description", "item_code"],
			)
		}
		for row in self.items:
			if not row.boq_item_row or row.boq_item_row not in boq_items:
				frappe.throw(_("Row #{0}: missing or invalid BOQ item reference.").format(row.idx))
			src = boq_items[row.boq_item_row]
			row.boq_qty = flt(src.qty)
			row.rate = flt(src.rate)
			row.uom = src.uom
			row.description = src.description
			row.item_code = src.item_code
			row.prev_cumulative_qty = flt(prev.get(row.boq_item_row, 0), 4)

	def compute_amounts(self):
		self.gross_amount = billing.compute_current_rows(
			self.items, limit_field="boq_qty", limit_label=_("BOQ qty")
		)
		if self.gross_amount <= 0:
			frappe.throw(_("This IPC has no measured progress (gross is zero)."))

		retention = flt(self.gross_amount * flt(self.retention_percent) / 100.0, 2)
		net = flt(
			self.gross_amount
			- retention
			- flt(self.advance_recovery_amount)
			- flt(self.other_deductions),
			2,
		)
		if net < 0:
			frappe.throw(_("Net certified cannot be negative. Review deductions."))
		self.retention_amount = retention
		self.net_certified = net

	def set_title(self):
		self.title = _("IPC-{0} | {1}").format(self.ipc_number, self.boq)

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 2:
			self.status = "Cancelled"
		elif self.docstatus == 1:
			self.status = "Invoiced" if self.sales_invoice else "Submitted"

	def on_submit(self):
		if billing.get_settings().auto_create_sales_invoice:
			self.create_sales_invoice()
		self._refresh_boq_tracking()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Sales Invoice",)
		if self.sales_invoice and frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus") == 1:
			frappe.throw(
				_("Cancel the linked Sales Invoice {0} before cancelling this IPC.").format(self.sales_invoice)
			)
		self.db_set("status", "Cancelled")
		self._refresh_boq_tracking()

	def _refresh_boq_tracking(self):
		from neotec_build.neotec_build.doctype.boq.boq import update_boq_item_tracking

		update_boq_item_tracking(self.boq)

	def create_sales_invoice(self):
		"""Draft SI at gross value. Taxes/ZATCA handled downstream by the
		ERPGulf ZATCA app on the Sales Invoice itself."""
		item_code = billing.require_company_account(
			self.company, "contract_income_item", _("Contract Revenue Item")
		)
		si = frappe.new_doc("Sales Invoice")
		si.update(
			{
				"customer": self.customer,
				"company": self.company,
				"project": self.project,
				"posting_date": self.measurement_date or nowdate(),
				"neotec_ipc": self.name,
				"neotec_retention_amount": self.retention_amount,
			}
		)
		si.append(
			"items",
			{
				"item_code": item_code,
				"qty": 1,
				"rate": self.gross_amount,
				"description": _("Contract works — {0} (IPC {1})").format(self.boq, self.ipc_number),
				"project": self.project,
			},
		)
		si.flags.ignore_permissions = True
		si.insert()
		self.db_set("sales_invoice", si.name)
		self.db_set("status", "Invoiced")
		frappe.msgprint(
			_("Draft Sales Invoice {0} created. Apply VAT and submit — ZATCA e-invoicing is handled by the ERPGulf app.").format(
				frappe.utils.get_link_to_form("Sales Invoice", si.name)
			),
			alert=True,
			indicator="green",
		)


@frappe.whitelist()
def make_ipc(boq):
	"""Prepare a draft IPC pre-filled with all BOQ rows and cumulative history."""
	frappe.has_permission("Interim Payment Certificate", "create", throw=True)
	boq_doc = frappe.get_doc("BOQ", boq)
	if boq_doc.status != "Active":
		frappe.throw(_("BOQ must be Active."))

	ipc = frappe.new_doc("Interim Payment Certificate")
	ipc.boq = boq_doc.name
	for row in boq_doc.items:
		ipc.append(
			"items",
			{
				"boq_item_row": row.name,
				"item_code": row.item_code,
				"description": row.description,
				"uom": row.uom,
				"boq_qty": row.qty,
				"rate": row.rate,
				"cumulative_qty": flt(row.billed_qty),
			},
		)
	return ipc.as_dict()
