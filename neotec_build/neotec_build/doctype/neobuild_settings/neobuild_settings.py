# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class NeoBuildSettings(Document):
	def validate(self):
		if flt(self.default_retention_percent) > flt(self.max_retention_percent):
			frappe.throw(_("Default Retention % cannot exceed Maximum Retention %."))
		seen = set()
		for row in self.company_defaults or []:
			if row.company in seen:
				frappe.throw(_("Duplicate company row: {0}").format(row.company))
			seen.add(row.company)
