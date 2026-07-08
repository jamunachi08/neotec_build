// Copyright (c) 2026, Neotec Integrated Solution
// License: MIT

frappe.ui.form.on("Subcontract Work Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && ["In Progress", "Completed"].includes(frm.doc.status)) {
			frm.add_custom_button(__("RA Bill"), () => {
				frappe.call({
					method: "neotec_build.neotec_build.doctype.ra_bill.ra_bill.make_ra_bill",
					args: { work_order: frm.docname },
					callback(r) {
						if (r.message) {
							const doc = frappe.model.sync(r.message)[0];
							frappe.set_route("Form", doc.doctype, doc.name);
						}
					},
				});
			}, __("Create"));
		}
	},
});

frappe.ui.form.on("Subcontract Work Order Item", {
	qty(frm, cdt, cdn) { compute_row(frm, cdt, cdn); },
	rate(frm, cdt, cdn) { compute_row(frm, cdt, cdn); },
});

function compute_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}
