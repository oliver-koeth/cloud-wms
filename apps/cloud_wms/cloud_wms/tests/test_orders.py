import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from cloud_wms.api import orders
from cloud_wms.tests.utils import ensure_master_data, ensure_user

PREFIX = "test-cwms-order-"
SOURCE = "test-source"
INTAKE_USER = "wms-test-intake@example.com"
PICKER_USER = "wms-test-picker@example.com"


class TestOrderIngest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.master = ensure_master_data()
		ensure_user(INTAKE_USER, ("Sales User", "WMS Intake"))
		ensure_user(PICKER_USER, ("WMS Picker",))
		frappe.db.commit()

	def setUp(self):
		frappe.set_user(INTAKE_USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._purge()

	def _purge(self):
		for name in frappe.get_all("Sales Order", filters={"cloud_wms_source": SOURCE}, pluck="name"):
			doc = frappe.get_doc("Sales Order", name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Sales Order", name, force=True)
		frappe.db.delete("WMS Request", {"idempotency_key": ["like", f"{PREFIX}%"]})
		frappe.db.delete("WMS Task Event", {"event_type": "Order Received", "actor": INTAKE_USER})
		frappe.db.commit()

	def ingest(self, key, external_id="EXT-1", lines=None, **overrides):
		args = {
			"idempotency_key": f"{PREFIX}{key}",
			"source": SOURCE,
			"external_order_id": external_id,
			"customer": self.master["customer"],
			"company": self.master["company"],
			"delivery_date": add_days(nowdate(), 3),
			"lines": lines if lines is not None else [{"item_code": self.master["item"], "qty": 2, "rate": 10}],
		}
		args.update(overrides)
		return orders.ingest(**args)

	def sales_orders(self, external_id=None):
		filters = {"cloud_wms_source": SOURCE}
		if external_id:
			filters["cloud_wms_external_order_id"] = external_id
		return frappe.get_all("Sales Order", filters=filters, fields=["name", "docstatus"])

	def test_creates_a_submitted_sales_order_without_a_pick_list(self):
		response = self.ingest("create-1", lines=[
			{"item_code": self.master["item"], "qty": 2, "rate": 10},
			{"item_code": self.master["item_2"], "qty": 1},
		])

		data = response["data"]
		self.assertEqual(data["docstatus"], 1)
		self.assertEqual(data["status"], "To Deliver and Bill")
		self.assertIsNone(data["pick_list"])
		self.assertFalse(data["duplicate"])
		order = frappe.get_doc("Sales Order", data["sales_order"])
		self.assertEqual(len(order.items), 2)
		self.assertEqual(order.cloud_wms_source, SOURCE)
		self.assertEqual(order.cloud_wms_external_order_id, "EXT-1")
		self.assertTrue(
			frappe.db.exists(
				"WMS Task Event",
				{"event_type": "Order Received", "sales_order": order.name, "actor": INTAKE_USER},
			)
		)

	def test_retry_with_same_key_creates_exactly_one_order(self):
		first = self.ingest("retry-1")
		second = self.ingest("retry-1")

		self.assertTrue(second["replayed"])
		self.assertEqual(first["data"], second["data"])
		self.assertEqual(len(self.sales_orders("EXT-1")), 1)

	def test_duplicate_external_id_with_new_key_returns_the_existing_order(self):
		first = self.ingest("dup-1")
		second = self.ingest("dup-2")

		self.assertTrue(second["data"]["duplicate"])
		self.assertEqual(second["data"]["sales_order"], first["data"]["sales_order"])
		self.assertEqual(len(self.sales_orders("EXT-1")), 1)

	def test_orders_without_an_external_id_are_never_treated_as_duplicates(self):
		self.ingest("noext-1", external_id=None)
		self.ingest("noext-2", external_id=None)

		self.assertEqual(len(self.sales_orders()), 2)

	def test_validation_failure_leaves_no_order_and_is_replayed(self):
		bad_lines = [{"item_code": "NO-SUCH-ITEM", "qty": 1}]

		first = self.ingest("fail-1", lines=bad_lines)
		self.assertEqual(first["error"]["code"], "VALIDATION_FAILED")
		self.assertEqual(frappe.local.response["http_status_code"], 422)
		self.assertEqual(self.sales_orders(), [])
		self.assertEqual(
			frappe.db.get_value("WMS Request", {"idempotency_key": f"{PREFIX}fail-1"}, "status"), "Failed"
		)

		second = self.ingest("fail-1", lines=bad_lines)
		self.assertEqual(second["error"]["code"], "VALIDATION_FAILED")

	def test_malformed_requests_are_rejected_with_400(self):
		for case, overrides in {
			"no-lines": {"lines": []},
			"zero-qty": {"lines": [{"item_code": self.master["item"], "qty": 0}]},
			"bad-source": {"source": "Bad Source!"},
		}.items():
			response = self.ingest(f"bad-{case}", **overrides)
			self.assertEqual(response["error"]["code"], "INVALID_REQUEST", case)
			self.assertEqual(frappe.local.response["http_status_code"], 400)
		self.assertEqual(self.sales_orders(), [])

	def test_user_without_intake_role_is_forbidden(self):
		frappe.set_user(PICKER_USER)

		response = self.ingest("forbidden-1")

		self.assertEqual(response["error"]["code"], "FORBIDDEN")
		self.assertEqual(frappe.local.response["http_status_code"], 403)
		self.assertEqual(self.sales_orders(), [])
