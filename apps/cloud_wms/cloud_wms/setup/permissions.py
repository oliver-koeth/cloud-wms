import frappe
from frappe.permissions import setup_custom_perms

ROLES = ("WMS Intake", "WMS Picker", "WMS Dispatch", "WMS Supervisor")

READ = ("read",)
WRITE = ("read", "write", "create")
SUBMIT = ("read", "write", "create", "submit")
CANCEL = ("read", "write", "create", "submit", "cancel")

# Standard ERPNext roles are left untouched except that the first custom rule for a doctype freezes
# its stock DocPerm rows into Custom DocPerm (Frappe behaviour), which this app then extends.
MATRIX = {
	"Sales Order": {
		"WMS Intake": SUBMIT,
		"WMS Picker": READ,
		"WMS Dispatch": READ,
		"WMS Supervisor": READ,
	},
	"Pick List": {
		"WMS Picker": SUBMIT,
		"WMS Dispatch": READ,
		"WMS Supervisor": CANCEL,
	},
	"Stock Reservation Entry": {
		"WMS Picker": SUBMIT,
		"WMS Supervisor": CANCEL,
	},
	"Delivery Note": {
		"WMS Dispatch": SUBMIT,
		"WMS Supervisor": READ,
	},
}

PTYPES = ("read", "write", "create", "submit", "cancel", "delete")


def ensure_roles():
	for role in ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
			ignore_permissions=True
		)


def ensure_permissions():
	for doctype, by_role in MATRIX.items():
		setup_custom_perms(doctype)
		for role, granted in by_role.items():
			_ensure_rule(doctype, role, granted)
		frappe.clear_cache(doctype=doctype)


def _ensure_rule(doctype, role, granted):
	name = frappe.db.get_value(
		"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	)
	values = {ptype: 1 if ptype in granted else 0 for ptype in PTYPES}
	if name:
		frappe.db.set_value("Custom DocPerm", name, values, update_modified=False)
		return
	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": role,
			"permlevel": 0,
			**values,
		}
	).insert(ignore_permissions=True)
