// Copyright (c) 2026, Neotec Integrated Solution
// License: MIT

frappe.ui.form.on("RA Bill", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.purchase_invoice) {
			frm.add_custom_button(__("Purchase Invoice"), () =>
				frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice), __("View"));
		}
		if (frm.doc.docstatus === 1 && frm.doc.retention_journal_entry) {
			frm.add_custom_button(__("Retention JE"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.retention_journal_entry), __("View"));
		}
	},
});

frappe.ui.form.on("RA Bill Item", {
	cumulative_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const current = flt(row.cumulative_qty) - flt(row.prev_cumulative_qty);
		frappe.model.set_value(cdt, cdn, "current_qty", current);
		frappe.model.set_value(cdt, cdn, "amount", current * flt(row.rate));
	},
});
