// Copyright (c) 2026, Neotec Integrated Solution
// License: MIT

frappe.ui.form.on("Interim Payment Certificate", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () =>
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("View"));
		}
	},
});

frappe.ui.form.on("IPC Item", {
	cumulative_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const current = flt(row.cumulative_qty) - flt(row.prev_cumulative_qty);
		frappe.model.set_value(cdt, cdn, "current_qty", current);
		frappe.model.set_value(cdt, cdn, "amount", current * flt(row.rate));
	},
});
