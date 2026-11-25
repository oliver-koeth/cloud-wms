"""Local demo users, warehouse locations and stock. Never runs against a non-local site."""

import frappe
from frappe.utils import cint

DEMO_PASSWORD = "admin"
DEMO_ITEM = "WMS-DEMO-TOTE"
DEMO_QTY = 20
DEMO_RATE = 25

DEMO_USERS = {
	"sales@cloud-wms.local": {
		"username": "Sales",
		"first_name": "Sales",
		"roles": ("Sales User", "WMS Intake"),
	},
	"supervisor@cloud-wms.local": {
		"username": "Supervisor",
		"first_name": "Supervisor",
		"roles": ("WMS Supervisor", "WMS Picker", "WMS Dispatch"),
	},
	"worker@cloud-wms.local": {
		"username": "Worker",
		"first_name": "Worker",
		"roles": ("WMS Picker",),
	},
}

# (warehouse_name, parent warehouse_name, barcode); parents must precede children.
DEMO_LOCATIONS = (
	("MAIN", None, None),
	("MAIN-A", "MAIN", None),
	("MAIN-A-01", "MAIN-A", None),
	("MAIN-A-01-01", "MAIN-A-01", "LOC-MAIN-A-01-01"),
	("MAIN-A-01-02", "MAIN-A-01", "LOC-MAIN-A-01-02"),
	("MAIN-A-01-03", "MAIN-A-01", "LOC-MAIN-A-01-03"),
)


def assert_local_site():
	site = frappe.local.site
	local = site == "frontend" or site.endswith((".localhost", ".local"))
	if not (local or cint(frappe.conf.get("cloud_wms_demo_data"))):
		frappe.throw(
			f"Refusing to create demo data on site {site!r}. "
			"Set cloud_wms_demo_data in the site config to override."
		)


def setup_all():
	assert_local_site()
	frappe.set_user("Administrator")
	setup_users()
	company = get_company()
	locations = setup_locations(company)
	setup_stock(company, locations)
	frappe.db.commit()
	return {"company": company, "locations": locations}


def setup_users():
	assert_local_site()
	frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)
	for email, spec in DEMO_USERS.items():
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.new_doc("User")
			user.email = email
			user.send_welcome_email = 0
		user.first_name = spec["first_name"]
		user.username = spec["username"]
		user.enabled = 1
		user.user_type = "System User"
		user.new_password = DEMO_PASSWORD
		user.flags.ignore_password_policy = True
		have = {row.role for row in user.roles}
		for role in spec["roles"]:
			if role not in have:
				user.append("roles", {"role": role})
		user.save(ignore_permissions=True)


def get_company():
	company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw("No Company exists yet. Complete the ERPNext setup wizard first.")
	return company


def setup_locations(company):
	"""Create the demo hierarchy; returns {warehouse_name: erpnext_name}."""
	assert_local_site()
	names = {}
	for warehouse_name, parent, barcode in DEMO_LOCATIONS:
		is_leaf = barcode is not None
		existing = frappe.db.get_value("Warehouse", {"warehouse_name": warehouse_name, "company": company})
		if existing:
			names[warehouse_name] = existing
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": warehouse_name,
				"company": company,
				"is_group": 0 if is_leaf else 1,
				"parent_warehouse": names.get(parent),
				"cloud_wms_location_barcode": barcode,
			}
		).insert(ignore_permissions=True)
		names[warehouse_name] = doc.name
	return names


def setup_stock(company, locations):
	assert_local_site()
	if not frappe.db.exists("Item", DEMO_ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": DEMO_ITEM,
				"item_name": "WMS Demo Tote",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"standard_rate": DEMO_RATE,
			}
		).insert(ignore_permissions=True)

	rows = []
	for warehouse_name, _parent, barcode in DEMO_LOCATIONS:
		if barcode is None:
			continue
		warehouse = locations[warehouse_name]
		on_hand = frappe.db.get_value("Bin", {"item_code": DEMO_ITEM, "warehouse": warehouse}, "actual_qty")
		if not on_hand:
			rows.append(
				{
					"item_code": DEMO_ITEM,
					"t_warehouse": warehouse,
					"qty": DEMO_QTY,
					"basic_rate": DEMO_RATE,
				}
			)
	if rows:
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"company": company,
				"items": rows,
			}
		)
		entry.insert(ignore_permissions=True)
		entry.submit()
