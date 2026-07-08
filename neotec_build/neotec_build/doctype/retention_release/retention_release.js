// Copyright (c) 2026, Neotec Integrated Solution
// License: MIT

frappe.ui.form.on("Retention Release", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.journal_entry) {
			frm.add_custom_button(__("Journal Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry), __("View"));
		}
	},
	party(frm) { frm.trigger("refresh_held"); },
	work_order(frm) { frm.trigger("refresh_held"); },
	boq(frm) { frm.trigger("refresh_held"); },
	refresh_held(frm) {
		// retention_held recalculates server-side on validate
	},
});
