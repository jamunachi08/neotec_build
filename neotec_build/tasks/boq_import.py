# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

"""BOQ Excel import — heavy parsing runs as a background job per NeoBuild
architecture standards. Supports EN and AR column headers.

Expected columns (first sheet, first row = headers, order-independent):
	Section | Item Code | Description | UOM | Qty | Rate
Arabic equivalents are also recognised.
"""

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

HEADER_ALIASES = {
	"section": {"section", "division", "القسم", "الباب"},
	"item_code": {"item code", "code", "item", "رمز البند", "الرمز"},
	"description": {"description", "scope", "البند", "الوصف", "وصف البند"},
	"uom": {"uom", "unit", "الوحدة", "وحدة القياس"},
	"qty": {"qty", "quantity", "الكمية"},
	"rate": {"rate", "unit rate", "price", "السعر", "سعر الوحدة"},
}


def _map_headers(header_row):
	mapping = {}
	for idx, cell in enumerate(header_row):
		if cell is None:
			continue
		key = str(cell).strip().lower()
		for field, aliases in HEADER_ALIASES.items():
			if key in aliases:
				mapping[field] = idx
	return mapping


def enqueue_boq_import(boq, file_url):
	boq_doc = frappe.get_doc("BOQ", boq)
	if boq_doc.docstatus != 0:
		frappe.throw(_("BOQ items can only be imported into a draft BOQ."))
	frappe.enqueue(
		"neotec_build.tasks.boq_import.import_boq_items",
		queue="long",
		job_name=f"neobuild-boq-import-{boq}",
		boq=boq,
		file_url=file_url,
		user=frappe.session.user,
	)


def import_boq_items(boq, file_url, user=None):
	try:
		rows = read_xlsx_file_from_attached_file(file_url=file_url)
		if not rows or len(rows) < 2:
			raise frappe.ValidationError(_("The uploaded file has no data rows."))

		mapping = _map_headers(rows[0])
		missing = {"description", "uom", "qty", "rate"} - set(mapping)
		if missing:
			raise frappe.ValidationError(
				_("Missing required columns: {0}").format(", ".join(sorted(missing)))
			)

		boq_doc = frappe.get_doc("BOQ", boq)
		imported, skipped = 0, 0
		for raw in rows[1:]:
			def val(field):
				idx = mapping.get(field)
				return raw[idx] if idx is not None and idx < len(raw) else None

			description = val("description")
			if not description or not str(description).strip():
				skipped += 1
				continue

			uom = str(val("uom") or "").strip()
			if uom and not frappe.db.exists("UOM", uom):
				frappe.get_doc({"doctype": "UOM", "uom_name": uom}).insert(
					ignore_permissions=True, ignore_if_duplicate=True
				)

			boq_doc.append(
				"items",
				{
					"section": str(val("section") or "").strip() or None,
					"item_code": str(val("item_code") or "").strip() or None,
					"description": str(description).strip(),
					"uom": uom or None,
					"qty": flt(val("qty")),
					"rate": flt(val("rate")),
				},
			)
			imported += 1

		boq_doc.save(ignore_permissions=True)
		frappe.db.commit()
		_notify(user, boq, _("BOQ import complete: {0} rows imported, {1} skipped.").format(imported, skipped), "green")
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=f"NeoBuild BOQ import failed: {boq}")
		_notify(user, boq, _("BOQ import failed. Check Error Log for details."), "red")
		raise


def _notify(user, boq, message, indicator):
	if not user:
		return
	frappe.publish_realtime(
		"msgprint",
		{"message": message, "alert": True, "indicator": indicator},
		user=user,
	)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "BOQ",
			"reference_name": boq,
			"content": message,
		}
	).insert(ignore_permissions=True)
