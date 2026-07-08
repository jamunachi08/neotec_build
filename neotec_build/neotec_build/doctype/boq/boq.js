// Copyright (c) 2026, Neotec Integrated Solution
// License: MIT

frappe.ui.form.on("BOQ", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Import Items from Excel"), () => {
				new frappe.ui.FileUploader({
					doctype: frm.doctype,
					docname: frm.docname,
					allow_multiple: false,
					restrictions: { allowed_file_types: [".xlsx"] },
					on_success(file) {
						frappe.call({
							method: "neotec_build.api.import_boq_from_file",
							args: { boq: frm.docname, file_url: file.file_url },
							callback(r) {
								if (r.message) frappe.show_alert({ message: r.message.message, indicator: "blue" });
							},
						});
					},
				});
			});
		}

		if (frm.doc.docstatus === 1 && frm.doc.status === "Active") {
			frm.add_custom_button(__("Subcontract Work Order"), () => {
				frappe.call({
					method: "neotec_build.neotec_build.doctype.subcontract_work_order.subcontract_work_order.make_work_order_from_boq",
					args: { boq: frm.docname },
					callback(r) {
						if (r.message) {
							const doc = frappe.model.sync(r.message)[0];
							frappe.set_route("Form", doc.doctype, doc.name);
						}
					},
				});
			}, __("Create"));

			frm.add_custom_button(__("Interim Payment Certificate"), () => {
				frappe.call({
					method: "neotec_build.neotec_build.doctype.interim_payment_certificate.interim_payment_certificate.make_ipc",
					args: { boq: frm.docname },
					callback(r) {
						if (r.message) {
							const doc = frappe.model.sync(r.message)[0];
							frappe.set_route("Form", doc.doctype, doc.name);
						}
					},
				});
			}, __("Create"));

			frm.add_custom_button(__("Close BOQ"), () => {
				frm.call("close_boq").then(() => frm.reload_doc());
			});
		}
	},
});

frappe.ui.form.on("BOQ Item", {
	qty(frm, cdt, cdn) { compute_row(frm, cdt, cdn); },
	rate(frm, cdt, cdn) { compute_row(frm, cdt, cdn); },
});

function compute_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}
