# Copyright (c) 2026, Neotec Integrated Solution and contributors
# License: MIT. See license.txt

app_name = "neotec_build"
app_title = "NeoBuild"
app_publisher = "Neotec Integrated Solution"
app_description = (
	"Construction contracting suite for KSA: BOQ, subcontractor work orders, "
	"RA/progress billing, IPCs, retention and advance management."
)
app_email = "support@neotec.ai"
app_license = "MIT"

required_apps = ["erpnext"]

# Idempotent self-install (roles, custom fields, workspace)
after_install = "neotec_build.setup.install.after_install"
after_migrate = "neotec_build.setup.install.after_migrate"

# Business logic lives in versioned doctype controllers and
# neotec_build.utils.billing — no Server Scripts.

fixtures = []  # everything is created programmatically in setup.install
