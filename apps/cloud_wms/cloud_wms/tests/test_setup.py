import frappe
from frappe.tests import IntegrationTestCase

from cloud_wms.setup import demo, install, permissions


def _perm(doctype, role):
	return frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0},
		list(permissions.PTYPES),
		as_dict=True,
	)


class TestSetup(IntegrationTestCase):
	def test_ensure_setup_is_idempotent(self):
		install.ensure_setup()
		install.ensure_setup()
		for role in permissions.ROLES:
			self.assertEqual(frappe.db.count("Role", {"name": role}), 1)
		self.assertEqual(
			frappe.db.count("Custom DocPerm", {"parent": "Pick List", "role": "WMS Picker"}), 1
		)

	def test_roles_have_desk_access(self):
		for role in permissions.ROLES:
			self.assertEqual(frappe.db.get_value("Role", role, "desk_access"), 1)

	def test_custom_fields_exist(self):
		for doctype, fields in install.CUSTOM_FIELDS.items():
			for field in fields:
				self.assertTrue(frappe.db.exists("Custom Field", f"{doctype}-{field['fieldname']}"))

	def test_stock_reservation_is_enabled_but_not_automatic(self):
		install.ensure_stock_settings()
		self.assertEqual(frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"), 1)
		self.assertEqual(frappe.db.get_single_value("Stock Settings", "auto_reserve_stock"), 0)

	def test_permission_matrix(self):
		picker = _perm("Pick List", "WMS Picker")
		self.assertEqual((picker.read, picker.create, picker.submit, picker.cancel), (1, 1, 1, 0))
		self.assertEqual(picker.delete, 1)

		supervisor = _perm("Pick List", "WMS Supervisor")
		self.assertEqual((supervisor.cancel, supervisor.delete), (1, 1))

		intake = _perm("Sales Order", "WMS Intake")
		self.assertEqual((intake.create, intake.submit), (1, 1))
		self.assertEqual(_perm("Sales Order", "WMS Picker").write, 0)

		self.assertEqual(_perm("Delivery Note", "WMS Dispatch").submit, 1)
		self.assertIsNone(_perm("Delivery Note", "WMS Picker"))

		admin = _perm("Customer", "WMS Admin")
		self.assertEqual((admin.create, admin.write, admin.delete), (1, 1, 1))
		self.assertEqual(_perm("Sales Order", "WMS Admin").cancel, 1)
		self.assertIsNone(_perm("Customer", "WMS Supervisor"))

	def test_standard_erpnext_permissions_survive_freeze(self):
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": "Pick List", "role": "Stock User"}))
		self.assertTrue(frappe.db.exists("Custom DocPerm", {"parent": "Sales Order", "role": "Sales User"}))


class TestDemoUsers(IntegrationTestCase):
	def test_demo_users_have_expected_roles_and_usernames(self):
		demo.setup_users()
		demo.setup_users()

		expected = {
			"sales@cloud-wms.local": ("Sales", {"Sales User", "WMS Intake"}),
			"supervisor@cloud-wms.local": ("Supervisor", {"WMS Supervisor", "WMS Picker", "WMS Dispatch"}),
			"worker@cloud-wms.local": ("Worker", {"WMS Picker"}),
			"admin@cloud-wms.local": ("Admin", {"WMS Admin"}),
		}
		for email, (username, roles) in expected.items():
			self.assertEqual(frappe.db.get_value("User", email, "username"), username)
			self.assertTrue(roles <= set(frappe.get_roles(email)), email)
		self.assertNotIn("WMS Supervisor", frappe.get_roles("worker@cloud-wms.local"))

	def test_demo_customer_is_created_once(self):
		demo.setup_customer()
		demo.setup_customer()

		self.assertEqual(frappe.db.count("Customer", {"name": demo.DEMO_CUSTOMER}), 1)

	def test_demo_setup_refuses_non_local_sites(self):
		original = frappe.local.site
		frappe.local.site = "wms.example.com"
		try:
			with self.assertRaises(frappe.ValidationError):
				demo.assert_local_site()
		finally:
			frappe.local.site = original
