# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from neotec_build.utils import billing


class RetentionRelease(Document):
	def validate(self):
		self.set_retention_held()
		self.apply_release_type()
		self.validate_amount()

	def set_retention_held(self):
		self.retention_held = billing.get_retention_held(
			self.party_type,
			self.party,
			self.company,
			work_order=self.work_order if self.party_type == "Supplier" else None,
			boq=self.boq if self.party_type == "Customer" else None,
		)

	def apply_release_type(self):
		if self.release_type == "First Moiety (50%)" and not flt(self.amount):
			self.amount = flt(self.retention_held * 0.5, 2)
		elif self.release_type == "Final Release" and not flt(self.amount):
			self.amount = flt(self.retention_held, 2)

	def validate_amount(self):
		if flt(self.amount) <= 0:
			frappe.throw(_("Release amount must be greater than zero."))
		if flt(self.amount) > flt(self.retention_held):
			frappe.throw(
				_("Release amount ({0}) exceeds retention currently held ({1}).").format(
					self.amount, self.retention_held
				)
			)

	def on_submit(self):
		self.create_journal_entry()

	def on_cancel(self):
		self.ignore_linked_doctypes = ("Journal Entry",)
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			frappe.throw(
				_("Cancel the linked Journal Entry {0} before cancelling this release.").format(self.journal_entry)
			)

	def create_journal_entry(self):
		"""Supplier: Dr Retention Payable / Cr Creditors (payable to subcontractor).
		Customer: Dr Debtors / Cr Retention Receivable (client now owes the retention)."""
		je = frappe.new_doc("Journal Entry")
		je.update(
			{
				"voucher_type": "Journal Entry",
				"company": self.company,
				"posting_date": self.release_date or nowdate(),
				"user_remark": _("Retention release {0} ({1})").format(self.name, self.release_type),
			}
		)

		if self.party_type == "Supplier":
			retention_account = billing.require_company_account(
				self.company, "retention_payable_account", _("Retention Payable Account")
			)
			creditors = frappe.get_cached_value("Company", self.company, "default_payable_account")
			je.append(
				"accounts",
				{
					"account": retention_account,
					"debit_in_account_currency": flt(self.amount),
					"project": self.project,
				},
			)
			je.append(
				"accounts",
				{
					"account": creditors,
					"party_type": "Supplier",
					"party": self.party,
					"credit_in_account_currency": flt(self.amount),
					"project": self.project,
				},
			)
		else:
			retention_account = billing.require_company_account(
				self.company, "retention_receivable_account", _("Retention Receivable Account")
			)
			debtors = frappe.get_cached_value("Company", self.company, "default_receivable_account")
			je.append(
				"accounts",
				{
					"account": debtors,
					"party_type": "Customer",
					"party": self.party,
					"debit_in_account_currency": flt(self.amount),
					"project": self.project,
				},
			)
			je.append(
				"accounts",
				{
					"account": retention_account,
					"credit_in_account_currency": flt(self.amount),
					"project": self.project,
				},
			)

		je.flags.ignore_permissions = True
		je.insert()
		self.db_set("journal_entry", je.name)
		frappe.msgprint(
			_("Draft Journal Entry {0} created for the retention release.").format(
				frappe.utils.get_link_to_form("Journal Entry", je.name)
			),
			alert=True,
			indicator="green",
		)
