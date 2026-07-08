# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from neotec_build.utils import billing


class RABill(Document):
	def validate(self):
		self.validate_work_order()
		self.set_ra_number()
		self.load_previous_cumulative()
		self.compute_amounts()
		self.set_title()
		self.set_status()

	def validate_work_order(self):
		wo = frappe.db.get_value(
			"Subcontract Work Order",
			self.work_order,
			["docstatus", "status", "retention_percent"],
			as_dict=True,
		)
		if not wo or wo.docstatus != 1:
			frappe.throw(_("Subcontract Work Order must be submitted."))
		if wo.status in ("Closed", "Cancelled"):
			frappe.throw(_("Work Order is {0}; billing is not allowed.").format(wo.status))
		self.retention_percent = flt(wo.retention_percent)

	def set_ra_number(self):
		if not self.ra_number:
			last = frappe.db.get_value(
				"RA Bill",
				{"work_order": self.work_order, "docstatus": 1},
				"max(ra_number)",
			)
			self.ra_number = (last or 0) + 1

	def load_previous_cumulative(self):
		"""prev_cumulative per WO row from previously *submitted* RA Bills."""
		prev = {}
		for bill in frappe.get_all(
			"RA Bill",
			filters={"work_order": self.work_order, "docstatus": 1, "name": ("!=", self.name or "New")},
			pluck="name",
		):
			for row in frappe.get_all(
				"RA Bill Item", filters={"parent": bill}, fields=["wo_item_row", "current_qty"]
			):
				if row.wo_item_row:
					prev[row.wo_item_row] = prev.get(row.wo_item_row, 0) + flt(row.current_qty)

		wo_items = {
			row.name: row
			for row in frappe.get_all(
				"Subcontract Work Order Item",
				filters={"parent": self.work_order},
				fields=["name", "qty", "rate", "uom", "description", "item_code"],
			)
		}
		for row in self.items:
			if not row.wo_item_row or row.wo_item_row not in wo_items:
				frappe.throw(_("Row #{0}: missing or invalid Work Order item reference.").format(row.idx))
			src = wo_items[row.wo_item_row]
			row.wo_qty = flt(src.qty)
			row.rate = flt(src.rate)
			row.uom = src.uom
			row.description = src.description
			row.item_code = src.item_code
			row.prev_cumulative_qty = flt(prev.get(row.wo_item_row, 0), 4)

	def compute_amounts(self):
		self.gross_amount = billing.compute_current_rows(
			self.items, limit_field="wo_qty", limit_label=_("Work Order qty")
		)
		if self.gross_amount <= 0:
			frappe.throw(_("This RA Bill has no measured progress (gross is zero)."))

		wo = frappe.db.get_value(
			"Subcontract Work Order",
			self.work_order,
			["advance_amount", "advance_recovered", "advance_recovery_percent"],
			as_dict=True,
		)
		advance_outstanding = flt(wo.advance_amount) - flt(wo.advance_recovered)

		retention, advance_recovery, net = billing.compute_deductions(
			self.gross_amount,
			self.retention_percent,
			wo.advance_recovery_percent,
			advance_outstanding,
			self.other_deductions,
		)
		self.retention_amount = retention
		self.advance_recovery_amount = advance_recovery
		self.net_payable = net

	def set_title(self):
		self.title = _("RA-{0} | {1}").format(self.ra_number, self.work_order)

	def set_status(self):
		if self.docstatus == 0:
			self.status = "Draft"
		elif self.docstatus == 2:
			self.status = "Cancelled"
		elif self.docstatus == 1:
			self.status = "Invoiced" if self.purchase_invoice else "Submitted"

	def on_submit(self):
		settings = billing.get_settings()
		if settings.auto_create_purchase_invoice:
			self.create_purchase_invoice()
		if settings.auto_create_retention_je and (
			flt(self.retention_amount) or flt(self.advance_recovery_amount)
		):
			self.create_retention_journal_entry()
		self._refresh_work_order()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Purchase Invoice", "Journal Entry")
		for field, doctype in (
			("purchase_invoice", "Purchase Invoice"),
			("retention_journal_entry", "Journal Entry"),
		):
			ref = self.get(field)
			if ref and frappe.db.get_value(doctype, ref, "docstatus") == 1:
				frappe.throw(
					_("Cancel the linked {0} {1} before cancelling this RA Bill.").format(doctype, ref)
				)
		self.db_set("status", "Cancelled")
		self._refresh_work_order()

	def _refresh_work_order(self):
		wo = frappe.get_doc("Subcontract Work Order", self.work_order)
		wo.update_billing_status()

	def create_purchase_invoice(self):
		"""Draft PI at gross value; retention + advance recovery are shifted off
		Creditors by the companion Journal Entry so the net creditor balance
		equals net_payable."""
		company = self.company
		item_code = billing.require_company_account(
			company, "subcontract_item", _("Subcontract Service Item")
		)
		expense_account = billing.get_company_defaults(company).get("subcontract_expense_account")

		pi = frappe.new_doc("Purchase Invoice")
		pi.update(
			{
				"supplier": self.supplier,
				"company": company,
				"project": self.project,
				"posting_date": self.measurement_date or nowdate(),
				"bill_no": self.name,
				"neotec_ra_bill": self.name,
				"neotec_retention_amount": self.retention_amount,
			}
		)
		pi.append(
			"items",
			{
				"item_code": item_code,
				"qty": 1,
				"rate": self.gross_amount,
				"description": _("Subcontract works — {0} (RA Bill {1})").format(
					self.work_order, self.ra_number
				),
				"project": self.project,
				"expense_account": expense_account,
			},
		)
		pi.flags.ignore_permissions = True
		pi.insert()
		self.db_set("purchase_invoice", pi.name)
		self.db_set("status", "Invoiced")
		frappe.msgprint(
			_("Draft Purchase Invoice {0} created. Review taxes (ZATCA handled by ERPGulf app) and submit.").format(
				frappe.utils.get_link_to_form("Purchase Invoice", pi.name)
			),
			alert=True,
			indicator="green",
		)

	def create_retention_journal_entry(self):
		"""Draft JE: Dr Creditors (supplier) / Cr Retention Payable and
		Cr Subcontractor Advance for the recovery portion."""
		company = self.company
		creditors = frappe.get_cached_value("Company", company, "default_payable_account")
		retention_account = None
		if flt(self.retention_amount):
			retention_account = billing.require_company_account(
				company, "retention_payable_account", _("Retention Payable Account")
			)
		advance_account = None
		if flt(self.advance_recovery_amount):
			advance_account = billing.require_company_account(
				company, "advance_account", _("Subcontractor Advance Account")
			)

		je = frappe.new_doc("Journal Entry")
		je.update(
			{
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": self.measurement_date or nowdate(),
				"user_remark": _("Retention/advance recovery for RA Bill {0}").format(self.name),
			}
		)
		total = flt(self.retention_amount) + flt(self.advance_recovery_amount)
		je.append(
			"accounts",
			{
				"account": creditors,
				"party_type": "Supplier",
				"party": self.supplier,
				"debit_in_account_currency": total,
				"project": self.project,
			},
		)
		if retention_account:
			je.append(
				"accounts",
				{
					"account": retention_account,
					"credit_in_account_currency": flt(self.retention_amount),
					"project": self.project,
				},
			)
		if advance_account:
			je.append(
				"accounts",
				{
					"account": advance_account,
					"credit_in_account_currency": flt(self.advance_recovery_amount),
					"project": self.project,
				},
			)
		je.flags.ignore_permissions = True
		je.insert()
		self.db_set("retention_journal_entry", je.name)


@frappe.whitelist()
def make_ra_bill(work_order):
	"""Prepare a draft RA Bill pre-filled with all WO rows and cumulative history."""
	frappe.has_permission("RA Bill", "create", throw=True)
	wo = frappe.get_doc("Subcontract Work Order", work_order)
	if wo.docstatus != 1:
		frappe.throw(_("Work Order must be submitted."))

	bill = frappe.new_doc("RA Bill")
	bill.work_order = wo.name
	for row in wo.items:
		bill.append(
			"items",
			{
				"wo_item_row": row.name,
				"item_code": row.item_code,
				"description": row.description,
				"uom": row.uom,
				"wo_qty": row.qty,
				"rate": row.rate,
				"cumulative_qty": flt(row.billed_qty),
			},
		)
	return bill.as_dict()
