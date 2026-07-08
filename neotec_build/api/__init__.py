# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

"""Whitelisted API for NeoBuild. All endpoints enforce role guards."""

import frappe
from frappe import _

NEOBUILD_ROLES = ("NeoBuild Manager", "NeoBuild User", "System Manager")


def _guard():
	if not set(frappe.get_roles()) & set(NEOBUILD_ROLES):
		frappe.throw(_("You need a NeoBuild role to perform this action."), frappe.PermissionError)


@frappe.whitelist()
def import_boq_from_file(boq, file_url):
	"""Enqueue BOQ Excel import (long queue)."""
	_guard()
	frappe.has_permission("BOQ", "write", doc=boq, throw=True)
	from neotec_build.tasks.boq_import import enqueue_boq_import

	enqueue_boq_import(boq, file_url)
	return {"status": "queued", "message": _("Import queued. You will be notified when it completes.")}


@frappe.whitelist()
def get_project_billing_summary(project):
	"""Project-level snapshot: BOQ value, certified to client, subcontract
	commitments, billed by subcontractors, retention positions."""
	_guard()
	frappe.has_permission("Project", "read", doc=project, throw=True)

	out = {
		"boq_value": 0,
		"client_certified_gross": 0,
		"client_retention_held_by_client": 0,
		"subcontract_committed": 0,
		"subcontract_billed_gross": 0,
		"retention_held_from_subcontractors": 0,
	}

	for boq in frappe.get_all(
		"BOQ", filters={"project": project, "docstatus": 1}, fields=["name", "total_amount"]
	):
		out["boq_value"] += boq.total_amount or 0
		ipc = frappe.get_all(
			"Interim Payment Certificate",
			filters={"boq": boq.name, "docstatus": 1},
			fields=["sum(gross_amount) as gross", "sum(retention_amount) as retention"],
		)[0]
		out["client_certified_gross"] += ipc.gross or 0
		out["client_retention_held_by_client"] += ipc.retention or 0

	wo_totals = frappe.get_all(
		"Subcontract Work Order",
		filters={"project": project, "docstatus": 1},
		fields=[
			"sum(total_amount) as committed",
			"sum(total_billed_amount) as billed",
			"sum(total_retention_held) as retention",
		],
	)[0]
	out["subcontract_committed"] = wo_totals.committed or 0
	out["subcontract_billed_gross"] = wo_totals.billed or 0
	out["retention_held_from_subcontractors"] = wo_totals.retention or 0

	return out
