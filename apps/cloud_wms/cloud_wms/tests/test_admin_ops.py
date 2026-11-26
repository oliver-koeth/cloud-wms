import frappe
from frappe.tests import IntegrationTestCase

from cloud_wms.api import admin as api
from cloud_wms.services import audit
from cloud_wms.tests.test_tasks import install_fields
from cloud_wms.tests.utils import TEST_ABBR, TEST_COMPANY, ensure_master_data, ensure_user

PREFIX = "test-cwms-ops-"
ADMIN = "wms-ops-admin@example.com"
SUPERVISOR = "wms-ops-supervisor@example.com"
# Own item and bins: stock left in shared test items would redirect picks in other modules.
ITEM = "WMS-OPS-ITEM"
BIN_1 = f"WMS OPS Bin 1 - {TEST_ABBR}"
BIN_2 = f"WMS OPS Bin 2 - {TEST_ABBR}"
GROUP = f"WMS OPS Zone - {TEST_ABBR}"
REFERENCE_PREFIX = "WMS OPS Ref"


class TestAdminOps(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_master_data()
		install_fields()
		ensure_user(ADMIN, ("WMS Admin",))
		ensure_user(SUPERVISOR, ("WMS Supervisor",))
		for purpose in ("Material Receipt", "Material Transfer"):
			if not frappe.db.exists("Stock Entry Type", purpose):
				frappe.get_doc(
					{"doctype": "Stock Entry Type", "__newname": purpose, "purpose": purpose}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Warehouse", GROUP):
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": "WMS OPS Zone",
					"is_group": 1,
					"company": TEST_COMPANY,
				}
			).insert(ignore_permissions=True)
		for name in ("WMS OPS Bin 1", "WMS OPS Bin 2"):
			if not frappe.db.exists("Warehouse", f"{name} - {TEST_ABBR}"):
				frappe.get_doc(
					{
						"doctype": "Warehouse",
						"warehouse_name": name,
						"parent_warehouse": GROUP,
						"company": TEST_COMPANY,
					}
				).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer Group", {"parent_customer_group": ["is", "not set"]}):
			# The setup wizard creates the root on a real site; the test site skips it.
			frappe.get_doc(
				{"doctype": "Customer Group", "customer_group_name": "All Customer Groups", "is_group": 1}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": "WMS OPS Item",
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			).insert(ignore_permissions=True)
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
		postings = frappe.db.sql(
			"""
			select 'Stock Entry' as doctype, se.name, se.creation from `tabStock Entry` se
			where se.docstatus = 1 and exists (
				select 1 from `tabStock Entry Detail` d where d.parent = se.name and d.item_code = %(item)s)
			union all
			select 'Stock Reconciliation', sr.name, sr.creation from `tabStock Reconciliation` sr
			where sr.docstatus = 1 and exists (
				select 1 from `tabStock Reconciliation Item` d where d.parent = sr.name and d.item_code = %(item)s)
			order by creation desc
			""",
			{"item": ITEM},
			as_dict=True,
		)
		for row in postings:
			frappe.get_doc(row.doctype, row.name).cancel()
		for doctype in ("Customer Group", "Territory", "Item Group"):
			for name in frappe.get_all(
				doctype, filters={"name": ["like", f"{REFERENCE_PREFIX}%"]}, pluck="name", order_by="lft desc"
			):
				frappe.delete_doc(doctype, name, force=True)
		frappe.db.delete("WMS Task Event", {"item_code": ITEM})
		frappe.db.delete("WMS Task Event", {"actor": ["in", (ADMIN, SUPERVISOR)]})
		frappe.db.delete("WMS Request", {"idempotency_key": ["like", f"{PREFIX}%"]})
		frappe.db.commit()

	def call(self, fn, user=ADMIN, **kwargs):
		frappe.set_user(user)
		if fn.__name__.startswith(("post_", "cancel_", "create_")):
			kwargs.setdefault("idempotency_key", f"{PREFIX}{fn.__name__}-{frappe.generate_hash(length=8)}")
		return fn(**kwargs)

	def ok(self, response):
		self.assertNotIn("error", response, response)
		return response["data"]

	def err(self, response, code):
		self.assertIn("error", response, response)
		self.assertEqual(response["error"]["code"], code, response)
		return response["error"]

	def qty(self, warehouse):
		return frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": warehouse}, "actual_qty") or 0

	def post(self, purpose, qty, to_warehouse, user=ADMIN, **kwargs):
		return self.call(
			api.post_stock,
			user=user,
			purpose=purpose,
			item_code=ITEM,
			qty=qty,
			to_warehouse=to_warehouse,
			**kwargs,
		)

	def test_stock_and_settings_screens_are_admin_only(self):
		for fn in (api.list_stock, api.list_postings, api.list_events, api.settings):
			self.err(self.call(fn, user=SUPERVISOR), "FORBIDDEN")
		self.err(self.post("receipt", 1, BIN_1, user=SUPERVISOR), "FORBIDDEN")
		self.err(self.call(api.list_reference, user=SUPERVISOR, doctype="UOM"), "FORBIDDEN")

	def test_receipt_transfer_count_and_cancel_post_through_erpnext(self):
		receipt = self.ok(self.post("receipt", 10, BIN_1, rate=5, reason="Initial delivery"))
		self.assertEqual(
			(receipt["doctype"], receipt["purpose"], receipt["docstatus"]),
			("Stock Entry", "Material Receipt", 1),
		)
		self.assertEqual(self.qty(BIN_1), 10)

		transfer = self.ok(self.post("transfer", 4, BIN_2, from_warehouse=BIN_1))
		self.assertEqual((transfer["from_warehouse"], transfer["to_warehouse"]), (BIN_1, BIN_2))
		self.assertEqual((self.qty(BIN_1), self.qty(BIN_2)), (6, 4))

		count = self.ok(self.post("count", 7, BIN_2, reason="Cycle count"))
		self.assertEqual((count["doctype"], count["docstatus"]), ("Stock Reconciliation", 1))
		self.assertEqual(self.qty(BIN_2), 7)

		levels = self.ok(self.call(api.list_stock, search=ITEM))
		self.assertEqual({row["warehouse"]: row["actual_qty"] for row in levels}, {BIN_1: 6, BIN_2: 7})
		self.assertEqual(len(self.ok(self.call(api.list_stock, warehouse=GROUP))), 2)
		postings = self.ok(self.call(api.list_postings, search=ITEM))
		self.assertEqual(
			[row["name"] for row in postings][:3], [count["name"], transfer["name"], receipt["name"]]
		)

		stale = self.call(
			api.cancel_posting, doctype="Stock Reconciliation", name=count["name"], modified="2000-01-01"
		)
		self.err(stale, "STALE")
		cancelled = self.ok(
			self.call(
				api.cancel_posting,
				doctype="Stock Reconciliation",
				name=count["name"],
				modified=count["modified"],
			)
		)
		self.assertEqual(cancelled["docstatus"], 2)
		self.assertEqual(self.qty(BIN_2), 4)

		events = frappe.get_all(
			"WMS Task Event", filters={"item_code": ITEM, "event_type": "Inventory Corrected"}, pluck="actor"
		)
		self.assertEqual(events, [ADMIN] * 4)

	def test_postings_are_validated(self):
		self.err(self.post("issue", 1, BIN_1), "INVALID_REQUEST")
		self.err(self.post("receipt", 0, BIN_1, rate=1), "INVALID_REQUEST")
		self.err(self.post("receipt", "abc", BIN_1, rate=1), "INVALID_REQUEST")
		self.err(self.post("receipt", 1, BIN_1, rate=-1), "INVALID_REQUEST")
		self.err(self.post("receipt", 1, GROUP, rate=1), "INVALID_REQUEST")
		self.err(self.post("transfer", 1, BIN_1, from_warehouse=BIN_1), "INVALID_REQUEST")
		# ERPNext refuses to move stock that is not there.
		self.err(self.post("transfer", 1, BIN_2, from_warehouse=BIN_1), "VALIDATION_FAILED")
		self.err(self.call(api.cancel_posting, doctype="Sales Order", name="x"), "INVALID_REQUEST")
		self.assertEqual(self.qty(BIN_1), 0)

	def test_audit_log_filters_events(self):
		frappe.set_user(ADMIN)
		audit.reset_correlation_id()
		frappe.local.cloud_wms_correlation_id = "ops-audit-test"
		audit.record_event("Inventory Corrected", item_code=ITEM, qty=1, details={"action": "test"})
		audit.record_event("Master Data Changed", details={"doctype": "Item", "name": ITEM})
		audit.reset_correlation_id()

		both = self.ok(self.call(api.list_events, correlation_id="ops-audit-test"))
		self.assertEqual(
			{row["event_type"] for row in both["events"]}, {"Inventory Corrected", "Master Data Changed"}
		)
		self.assertIn("Delivery Cancelled", both["event_types"])
		one = self.ok(
			self.call(api.list_events, correlation_id="ops-audit-test", event_type="Inventory Corrected")
		)
		self.assertEqual([row["item_code"] for row in one["events"]], [ITEM])
		today = frappe.utils.nowdate()
		self.assertEqual(
			len(self.ok(self.call(api.list_events, actor=ADMIN, from_date=today, to_date=today))["events"]), 2
		)
		self.assertEqual(self.ok(self.call(api.list_events, actor=ADMIN, to_date="2000-01-01"))["events"], [])
		self.err(self.call(api.list_events, from_date="2026-02-01", to_date="2026-01-01"), "INVALID_REQUEST")
		self.err(self.call(api.list_events, from_date="not a date"), "INVALID_REQUEST")

	def test_reference_lists_read_and_create_groups(self):
		tree = self.ok(self.call(api.list_reference, doctype="Customer Group"))
		self.assertTrue(tree["tree"])
		root = tree["rows"][0]
		self.assertEqual((root["depth"], root["is_group"]), (0, 1))
		self.assertFalse(self.ok(self.call(api.list_reference, doctype="UOM"))["tree"])
		self.err(self.call(api.list_reference, doctype="User"), "INVALID_REQUEST")
		self.err(
			self.call(api.create_reference, doctype="UOM", name=f"{REFERENCE_PREFIX} Box"), "INVALID_REQUEST"
		)

		group = self.ok(
			self.call(
				api.create_reference, doctype="Customer Group", name=f"{REFERENCE_PREFIX} Retail", is_group=1
			)
		)
		self.assertEqual((group["parent"], group["is_group"]), (root["name"], 1))
		leaf = self.ok(
			self.call(
				api.create_reference,
				doctype="Customer Group",
				name=f"{REFERENCE_PREFIX} Shops",
				parent=group["name"],
			)
		)
		self.assertEqual(leaf["is_group"], 0)
		rows = {
			row["name"]: row
			for row in self.ok(self.call(api.list_reference, doctype="Customer Group"))["rows"]
		}
		self.assertEqual(rows[leaf["name"]]["depth"], 2)
		self.assertTrue(
			frappe.db.exists("WMS Task Event", {"event_type": "Master Data Changed", "actor": ADMIN})
		)
		self.err(
			self.call(api.create_reference, doctype="Customer Group", name=f"{REFERENCE_PREFIX} Retail"),
			"DUPLICATE",
		)
		self.err(
			self.call(
				api.create_reference,
				doctype="Customer Group",
				name=f"{REFERENCE_PREFIX} X",
				parent=leaf["name"],
			),
			"INVALID_REQUEST",
		)

	def test_settings_show_enforced_stock_reservation(self):
		data = self.ok(self.call(api.settings))
		self.assertEqual(data["stock"]["enable_stock_reservation"], 1)
		self.assertEqual(data["stock"]["auto_reserve_stock"], 0)
		self.assertEqual(data["enforced"], {"enable_stock_reservation": 1, "auto_reserve_stock": 0})
		self.assertIn(TEST_COMPANY, [row["name"] for row in data["companies"]])
		self.assertTrue(data["versions"]["erpnext"])
