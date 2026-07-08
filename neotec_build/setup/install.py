# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

"""Idempotent self-install for NeoBuild — safe on every migrate
(after_install and after_migrate both route here)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ["NeoBuild Manager", "NeoBuild User"]

CUSTOM_FIELDS = {
	"Project": [
		{
			"fieldname": "neobuild_section",
			"label": "NeoBuild Defaults",
			"fieldtype": "Section Break",
			"insert_after": "cost_center",
			"collapsible": 1,
		},
		{
			"fieldname": "neotec_retention_percent",
			"label": "Subcontractor Retention % (Project Default)",
			"fieldtype": "Percent",
			"insert_after": "neobuild_section",
			"description": "Overrides NeoBuild Settings for Work Orders on this project. Leave 0 to use the global default.",
		},
		{
			"fieldname": "neotec_advance_recovery_percent",
			"label": "Advance Recovery % (Project Default)",
			"fieldtype": "Percent",
			"insert_after": "neotec_retention_percent",
		},
		{
			"fieldname": "neobuild_col_break",
			"fieldtype": "Column Break",
			"insert_after": "neotec_advance_recovery_percent",
		},
		{
			"fieldname": "neotec_client_retention_percent",
			"label": "Client Retention % (Project Default)",
			"fieldtype": "Percent",
			"insert_after": "neobuild_col_break",
			"description": "Retention the client withholds on IPCs for this project. Leave 0 to use the global default.",
		},
	],
	"Purchase Invoice": [
		{
			"fieldname": "neotec_ra_bill",
			"label": "RA Bill",
			"fieldtype": "Link",
			"options": "RA Bill",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "bill_no",
		},
		{
			"fieldname": "neotec_retention_amount",
			"label": "Retention Withheld",
			"fieldtype": "Currency",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "neotec_ra_bill",
		},
	],
	"Sales Invoice": [
		{
			"fieldname": "neotec_ipc",
			"label": "Interim Payment Certificate",
			"fieldtype": "Link",
			"options": "Interim Payment Certificate",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "customer_name",
		},
		{
			"fieldname": "neotec_retention_amount",
			"label": "Retention Withheld by Client",
			"fieldtype": "Currency",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "neotec_ipc",
		},
	],
}


def after_install():
	ensure_setup()


def after_migrate():
	ensure_setup()


def ensure_setup():
	create_roles()
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
	create_workspace()
	frappe.db.commit()


def create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc(
				{"doctype": "Role", "role_name": role, "desk_access": 1}
			).insert(ignore_permissions=True)


def create_workspace():
	"""Step-by-step process workspace. Frappe v15 renders the `content`
	blocks; links/shortcuts child tables back them."""
	import json
	from frappe.utils import random_string

	name = "NeoBuild"

	def block(block_type, **data):
		return {"id": random_string(10), "type": block_type, "data": data}

	def header(text, col=12):
		return block("header", text=f'<span class="h4"><b>{text}</b></span>', col=col)

	def para(text, col=12):
		return block("paragraph", text=text, col=col)

	def shortcut(label, col=3):
		return block("shortcut", shortcut_name=label, col=col)

	def card(label, col=4):
		return block("card", card_name=label, col=col)

	content = [
		header("🏗️ NeoBuild — Construction Contracting"),
		para(
			"<b>Process:</b> BOQ ➊ → Subcontract Work Order ➋ → RA Bill ➌ "
			"(auto Purchase Invoice + Retention JE) → Client IPC ➍ "
			"(auto Sales Invoice → ZATCA via ERPGulf) → Retention Release ➎"
		),
		block("spacer", col=12),
		header("➊ Bill of Quantities", col=12),
		para("Create BOQ → <b>Import Items from Excel</b> (EN/AR headers) → Submit to activate. "
			"BOQ qty is the ceiling for subcontracting and client certification."),
		shortcut("BOQ", col=3),
		block("spacer", col=12),
		header("➋ Subcontract the Scope", col=12),
		para("From an Active BOQ: <b>Create → Subcontract Work Order</b>. Set retention %, "
			"mobilization advance and recovery %. Scope is capped at remaining BOQ qty."),
		shortcut("Subcontract Work Order", col=3),
		block("spacer", col=12),
		header("➌ Subcontractor Progress Billing (RA Bills)", col=12),
		para("From the Work Order: <b>Create → RA Bill</b>. Enter cumulative measured qty — "
			"previous qty, retention, advance recovery and net payable compute automatically. "
			"On submit: draft Purchase Invoice + retention Journal Entry."),
		shortcut("RA Bill", col=3),
		block("spacer", col=12),
		header("➍ Client Certification (IPC)", col=12),
		para("From the BOQ: <b>Create → Interim Payment Certificate</b>. On submit: draft "
			"Sales Invoice at gross — apply VAT and submit; ZATCA e-invoicing is handled by the ERPGulf app."),
		shortcut("Interim Payment Certificate", col=3),
		block("spacer", col=12),
		header("➎ Retention Management", col=12),
		para("Release retention at handover (<b>First Moiety 50%</b>) and after the defects "
			"liability period (<b>Final</b>). Amounts are capped at net retention held. "
			"Track both directions in the Retention Ledger."),
		shortcut("Retention Release", col=3),
		shortcut("Retention Ledger", col=3),
		block("spacer", col=12),
		header("⚙️ Setup & Browse", col=12),
		para("One-time: set defaults, company accounts and service items in NeoBuild Settings. "
			"Per-project overrides live on the Project (NeoBuild Defaults section)."),
		shortcut("NeoBuild Settings", col=3),
		card("Contracts", col=4),
		card("Progress Billing", col=4),
		card("Reports & Settings", col=4),
	]

	shortcuts = [
		{"label": "BOQ", "type": "DocType", "link_to": "BOQ", "doc_view": "List", "color": "Blue"},
		{"label": "Subcontract Work Order", "type": "DocType", "link_to": "Subcontract Work Order", "doc_view": "List", "color": "Orange"},
		{"label": "RA Bill", "type": "DocType", "link_to": "RA Bill", "doc_view": "List", "color": "Green"},
		{"label": "Interim Payment Certificate", "type": "DocType", "link_to": "Interim Payment Certificate", "doc_view": "List", "color": "Green"},
		{"label": "Retention Release", "type": "DocType", "link_to": "Retention Release", "doc_view": "List", "color": "Purple"},
		{"label": "Retention Ledger", "type": "Report", "link_to": "Retention Ledger", "doc_view": "", "color": "Grey"},
		{"label": "NeoBuild Settings", "type": "DocType", "link_to": "NeoBuild Settings", "doc_view": "", "color": "Grey"},
	]

	cards = {
		"Contracts": [("BOQ", "BOQ"), ("Subcontract Work Order", "Subcontract Work Order")],
		"Progress Billing": [
			("RA Bill", "RA Bill"),
			("Interim Payment Certificate", "Interim Payment Certificate"),
			("Retention Release", "Retention Release"),
		],
		"Reports & Settings": [
			("Retention Ledger", None),
			("NeoBuild Settings", "NeoBuild Settings"),
		],
	}

	if frappe.db.exists("Workspace", name):
		ws = frappe.get_doc("Workspace", name)
		ws.links = []
		ws.shortcuts = []
	else:
		ws = frappe.new_doc("Workspace")
		ws.update(
			{
				"name": name,
				"label": name,
				"title": name,
				"icon": "organization",
				"module": "Neotec Build",
				"public": 1,
			}
		)

	ws.content = json.dumps(content)

	for sc in shortcuts:
		ws.append("shortcuts", sc)

	for card_label, links in cards.items():
		ws.append(
			"links",
			{"type": "Card Break", "label": card_label, "link_count": len(links)},
		)
		for label, link_to in links:
			if link_to is None:
				ws.append(
					"links",
					{
						"type": "Link",
						"label": label,
						"link_type": "Report",
						"link_to": "Retention Ledger",
						"is_query_report": 1,
					},
				)
			else:
				ws.append(
					"links",
					{"type": "Link", "label": label, "link_type": "DocType", "link_to": link_to},
				)

	ws.flags.ignore_permissions = True
	ws.save() if not ws.is_new() else ws.insert(ignore_permissions=True)
