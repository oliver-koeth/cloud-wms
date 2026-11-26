import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from erpnext.regional.address_template.setup import set_up_address_templates

from cloud_wms.api import admin as api
from cloud_wms.services import tasks
from cloud_wms.tests.test_tasks import _ensure_stock, install_fields
from cloud_wms.tests.utils import TEST_ABBR, TEST_COMPANY, ensure_master_data, ensure_user

PREFIX = "test-cwms-admin-"
SOURCE = "test-admin-source"
ADMIN = "wms-adm-admin@example.com"
PICKER = "wms-adm-picker@example.com"
CUSTOMER = "WMS ADM Customer"
ITEM = "WMS-ADM-ITEM"
ZONE = "WMS ADM Zone"
BIN = "WMS ADM Bin"
STOCK_BIN = f"WMS ADM Stock - {TEST_ABBR}"
# Own stocked item so this module leaves no stock that would redirect picks in other test modules.
STOCKED = "WMS-ADMTEST-STOCKED"


class TestAdmin(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.master = ensure_master_data()
		install_fields()
		ensure_user(ADMIN, ("WMS Admin",))
		ensure_user(PICKER, ("WMS Picker",))
		if not frappe.db.exists("Address Template", {"is_default": 1}):
			# The setup wizard creates these on a real site; the test site skips it.
			set_up_address_templates(default_country="Germany")
		if not frappe.db.exists("Warehouse", STOCK_BIN):
			frappe.get_doc(
				{"doctype": "Warehouse", "warehouse_name": "WMS ADM Stock", "company": TEST_COMPANY}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", STOCKED):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": STOCKED,
					"item_name": STOCKED,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			).insert(ignore_permissions=True)
		_ensure_stock(STOCKED, STOCK_BIN, 20)
		frappe.db.commit()

	def setUp(self):
		self._purge()
		frappe.set_user(ADMIN)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._purge()

	def _purge(self):
		frappe.set_user("Administrator")
		orders = frappe.get_all(
			"Sales Order", filters={"cloud_wms_source": SOURCE}, pluck="name", order_by="creation desc"
		)
		for order in orders:
			for row in tasks.pick_lists_for_order(order):
				frappe.delete_doc("Pick List", row.name, force=True)
			doc = frappe.get_doc("Sales Order", order)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Sales Order", order, force=True)
		for customer in frappe.get_all("Customer", filters={"customer_name": ["like", "WMS ADM%"]}, pluck="name"):
			for link in frappe.get_all(
				"Dynamic Link",
				filters={"link_doctype": "Customer", "link_name": customer, "parenttype": ["in", ("Address", "Contact")]},
				fields=["parenttype", "parent"],
			):
				frappe.delete_doc(link.parenttype, link.parent, force=True)
			frappe.delete_doc("Customer", customer, force=True)
		for item in frappe.get_all("Item", filters={"item_code": ["like", "WMS-ADM-%"]}, pluck="name"):
			frappe.db.delete("Item Price", {"item_code": item})
			frappe.delete_doc("Item", item, force=True)
		for warehouse in frappe.get_all(
			"Warehouse", filters={"warehouse_name": ["in", (BIN, ZONE)]}, pluck="name", order_by="lft desc"
		):
			frappe.delete_doc("Warehouse", warehouse, force=True)
		if orders:
			frappe.db.delete("WMS Task Event", {"sales_order": ["in", orders]})
		frappe.db.delete("WMS Task Event", {"actor": ADMIN})
		frappe.db.delete("WMS Request", {"idempotency_key": ["like", f"{PREFIX}%"]})
		frappe.db.commit()

	def call(self, fn, user=ADMIN, **kwargs):
		frappe.set_user(user)
		if fn.__name__.startswith(("save_", "delete_", "cancel_", "amend_")):
			kwargs.setdefault("idempotency_key", f"{PREFIX}{fn.__name__}-{frappe.generate_hash(length=8)}")
		return fn(**kwargs)

	def ok(self, response):
		self.assertNotIn("error", response, response)
		return response["data"]

	def err(self, response, code):
		self.assertIn("error", response, response)
		self.assertEqual(response["error"]["code"], code, response)
		return response["error"]

	def order(self, customer=None, qty=2):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": customer or self.master["customer"],
				"company": TEST_COMPANY,
				"delivery_date": add_days(nowdate(), 3),
				"cloud_wms_source": SOURCE,
				"cloud_wms_external_order_id": "ADM-EXT-1",
				"items": [
					{"item_code": STOCKED, "qty": qty, "rate": 10, "delivery_date": add_days(nowdate(), 3)}
				],
			}
		)
		doc.insert()
		doc.submit()
		frappe.db.commit()
		frappe.set_user(ADMIN)
		return doc.name

	def test_only_admins_can_use_admin_endpoints(self):
		self.err(self.call(api.list_customers, user=PICKER), "FORBIDDEN")
		self.err(self.call(api.save_customer, user=PICKER, customer_name="WMS ADM Nope"), "FORBIDDEN")
		self.assertIn("customer_groups", self.ok(self.call(api.options)))

	def test_customer_create_update_with_contact_and_address(self):
		created = self.ok(
			self.call(
				api.save_customer,
				customer_name=CUSTOMER,
				email_id="buyer@example.com",
				mobile_no="+49 30 1234",
				address={"address_line1": "Dock 1", "city": "Berlin", "country": "Germany"},
			)
		)
		self.assertEqual(created["email_id"], "buyer@example.com")
		self.assertEqual(created["address"]["city"], "Berlin")
		self.assertTrue(created["customer_primary_contact"])

		updated = self.ok(
			self.call(
				api.save_customer,
				name=created["name"],
				customer_name=CUSTOMER,
				email_id="orders@example.com",
				mobile_no="",
				address={"address_line1": "Dock 2", "city": "Hamburg", "country": "Germany"},
				disabled=1,
				modified=created["modified"],
			)
		)
		self.assertEqual(updated["email_id"], "orders@example.com")
		self.assertFalse(updated["mobile_no"])
		self.assertEqual(updated["address"]["city"], "Hamburg")
		self.assertEqual(updated["customer_primary_address"], created["customer_primary_address"])
		self.assertEqual(updated["disabled"], 1)
		self.assertEqual(
			frappe.db.get_value("Contact", created["customer_primary_contact"], "email_id"), "orders@example.com"
		)
		names = [row["name"] for row in self.ok(self.call(api.list_customers, search="WMS ADM"))]
		self.assertNotIn(created["name"], names)
		names = [row["name"] for row in self.ok(self.call(api.list_customers, search="WMS ADM", include_disabled=1))]
		self.assertIn(created["name"], names)

		stale = self.call(api.save_customer, name=created["name"], customer_name=CUSTOMER, modified=created["modified"])
		self.err(stale, "STALE")

	def test_customer_in_use_cannot_be_deleted(self):
		unused = self.ok(self.call(api.save_customer, customer_name=f"{CUSTOMER} Unused"))
		self.ok(self.call(api.delete_record, doctype="Customer", name=unused["name"]))
		self.assertFalse(frappe.db.exists("Customer", unused["name"]))

		used = self.ok(self.call(api.save_customer, customer_name=CUSTOMER))
		frappe.db.commit()
		self.order(customer=used["name"])
		error = self.err(self.call(api.delete_record, doctype="Customer", name=used["name"]), "IN_USE")
		self.assertEqual(error["next_action"], "Disable it instead.")
		self.err(self.call(api.delete_record, doctype="Sales Order", name="x"), "INVALID_REQUEST")

	def test_item_with_barcodes_and_selling_rate(self):
		created = self.ok(
			self.call(api.save_item, item_code=ITEM, item_name="Admin item", barcodes=["ADM-EAN-1"], selling_rate=12.5)
		)
		self.assertEqual(created["barcodes"], ["ADM-EAN-1"])
		self.assertEqual(created["selling_rate"], 12.5)
		self.assertEqual(created["stock_uom"], "Nos")

		updated = self.ok(
			self.call(
				api.save_item,
				name=ITEM,
				item_name="Admin item v2",
				barcodes=["ADM-EAN-2", "ADM-EAN-1", "ADM-EAN-2"],
				selling_rate=15,
				modified=created["modified"],
			)
		)
		self.assertEqual(updated["item_name"], "Admin item v2")
		self.assertEqual(updated["barcodes"], ["ADM-EAN-2", "ADM-EAN-1"])
		self.assertEqual(updated["selling_rate"], 15)
		self.assertEqual(frappe.db.count("Item Price", {"item_code": ITEM}), 1)
		self.err(self.call(api.save_item, item_code=f"{ITEM}-2", barcodes=["ADM-EAN-1"]), "DUPLICATE")
		listed = next(row for row in self.ok(self.call(api.list_items, search="WMS-ADM")) if row["name"] == ITEM)
		self.assertEqual(listed["barcodes"], ["ADM-EAN-2", "ADM-EAN-1"])

	def test_location_tree_rules(self):
		self.err(
			self.call(api.save_location, warehouse_name=ZONE, is_group=1, barcode="ADM-LOC", company=TEST_COMPANY),
			"INVALID_REQUEST",
		)
		zone = self.ok(self.call(api.save_location, warehouse_name=ZONE, is_group=1, company=TEST_COMPANY))
		bin_ = self.ok(
			self.call(api.save_location, warehouse_name=BIN, parent_warehouse=zone["name"], barcode="ADM-LOC-1")
		)
		self.assertEqual((bin_["depth"], bin_["barcode"]), (zone["depth"] + 1, "ADM-LOC-1"))
		self.err(
			self.call(api.save_location, warehouse_name=f"{BIN} 2", parent_warehouse=bin_["name"]),
			"INVALID_REQUEST",
		)
		self.err(
			self.call(api.save_location, warehouse_name=f"{BIN} 3", parent_warehouse=zone["name"], barcode="ADM-LOC-1"),
			"DUPLICATE",
		)
		self.err(self.call(api.delete_record, doctype="Warehouse", name=zone["name"]), "VALIDATION_FAILED")
		self.ok(self.call(api.delete_record, doctype="Warehouse", name=bin_["name"]))
		self.ok(self.call(api.delete_record, doctype="Warehouse", name=zone["name"]))

	def test_cancel_and_amend_order(self):
		first = self.order(qty=2)
		amended = self.ok(
			self.call(
				api.amend_order,
				sales_order=first,
				lines=[{"item_code": STOCKED, "qty": 5, "rate": 11}],
				delivery_date=add_days(nowdate(), 5),
			)
		)
		self.assertEqual(frappe.db.get_value("Sales Order", first, "docstatus"), 2)
		self.assertEqual((amended["amended_from"], amended["docstatus"]), (first, 1))
		self.assertEqual(amended["items"][0]["qty"], 5)
		self.assertEqual(
			(amended["cloud_wms_source"], amended["cloud_wms_external_order_id"]), (SOURCE, "ADM-EXT-1")
		)
		self.assertTrue(frappe.db.exists("WMS Task Event", {"event_type": "Order Amended", "sales_order": amended["name"]}))
		self.err(
			self.call(api.amend_order, sales_order=first, lines=[{"item_code": STOCKED, "qty": 1}]),
			"CONFLICT",
		)

		cancelled = self.ok(self.call(api.cancel_order, sales_order=amended["name"], modified=amended["modified"]))
		self.assertEqual(cancelled["docstatus"], 2)
		self.assertTrue(frappe.db.exists("WMS Task Event", {"event_type": "Order Cancelled", "sales_order": amended["name"]}))

	def test_cancel_is_blocked_while_a_pick_task_is_open(self):
		order = self.order()
		frappe.set_user("Administrator")
		task = tasks.claim(order, assignee=PICKER)
		frappe.db.commit()

		detail = self.ok(self.call(api.get_order, name=order))
		self.assertIn(task["pick_list"], detail["cancel_blocker"]["message"])
		error = self.err(self.call(api.cancel_order, sales_order=order), "ORDER_IN_USE")
		self.assertIn("Release", error["next_action"])
		self.assertEqual(frappe.db.get_value("Sales Order", order, "docstatus"), 1)
