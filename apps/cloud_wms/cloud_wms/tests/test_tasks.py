import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from cloud_wms.api import tasks as api
from cloud_wms.services import tasks as service
from cloud_wms.tests.utils import TEST_ABBR, TEST_COMPANY, ensure_master_data, ensure_user

PREFIX = "test-cwms-task-"
SOURCE = "test-task-source"
PICKER = "wms-t3-picker@example.com"
OTHER_PICKER = "wms-t3-picker2@example.com"
SUPERVISOR = "wms-t3-supervisor@example.com"
INTAKE = "wms-t3-intake@example.com"
BIN_A = f"WMS T3 Bin A - {TEST_ABBR}"
BIN_B = f"WMS T3 Bin B - {TEST_ABBR}"
BARCODE_A = "T3-LOC-A"
BARCODE_B = "T3-LOC-B"
ITEM_BARCODE = "T3-EAN-0001"


def _ensure_warehouse(name, barcode, parent=None, is_group=0):
	full_name = f"{name} - {TEST_ABBR}"
	if not frappe.db.exists("Warehouse", full_name):
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": name,
				"company": TEST_COMPANY,
				"parent_warehouse": parent,
				"is_group": is_group,
			}
		).insert(ignore_permissions=True)
	frappe.db.set_value("Warehouse", full_name, "cloud_wms_location_barcode", barcode)
	return full_name


def _ensure_stock(item, warehouse, qty):
	have = frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty") or 0
	if have >= qty:
		return
	if not frappe.db.exists("Stock Entry Type", "Material Receipt"):
		frappe.get_doc(
			{"doctype": "Stock Entry Type", "__newname": "Material Receipt", "purpose": "Material Receipt"}
		).insert(ignore_permissions=True)
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": TEST_COMPANY,
			"items": [
				{"item_code": item, "qty": qty - have, "basic_rate": 10, "t_warehouse": warehouse}
			],
		}
	)
	entry.insert(ignore_permissions=True)
	entry.submit()


class TestTasks(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.master = ensure_master_data()
		install_fields()
		cls.item = cls.master["item"]
		cls.item_2 = cls.master["item_2"]
		for email, roles in (
			(PICKER, ("WMS Picker",)),
			(OTHER_PICKER, ("WMS Picker",)),
			(SUPERVISOR, ("WMS Supervisor", "WMS Picker")),
			(INTAKE, ("Sales User", "WMS Intake")),
		):
			ensure_user(email, roles)
		cls.bin_a = _ensure_warehouse("WMS T3 Bin A", BARCODE_A)
		cls.bin_b = _ensure_warehouse("WMS T3 Bin B", BARCODE_B)
		_ensure_stock(cls.item, cls.bin_a, 50)
		_ensure_stock(cls.item_2, cls.bin_b, 50)
		item = frappe.get_doc("Item", cls.item)
		if not any(row.barcode == ITEM_BARCODE for row in item.barcodes):
			item.append("barcodes", {"barcode": ITEM_BARCODE})
			item.save(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		self._purge()
		frappe.set_user(PICKER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		self._purge()

	def _purge(self):
		frappe.set_user("Administrator")
		orders = frappe.get_all("Sales Order", filters={"cloud_wms_source": SOURCE}, pluck="name")
		for order in orders:
			for row in service.pick_lists_for_order(order):
				pick = frappe.get_doc("Pick List", row.name)
				if pick.docstatus == 1:
					pick.cancel_stock_reservation_entries(notify=False)
					pick.cancel()
				frappe.delete_doc("Pick List", row.name, force=True)
			so = frappe.get_doc("Sales Order", order)
			if so.docstatus == 1:
				so.cancel()
			frappe.delete_doc("Sales Order", order, force=True)
		if orders:
			frappe.db.delete("WMS Task Event", {"sales_order": ["in", orders]})
		frappe.db.delete("WMS Request", {"idempotency_key": ["like", f"{PREFIX}%"]})
		frappe.db.commit()

	def order(self, lines=None):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.master["customer"],
				"company": self.master["company"],
				"delivery_date": add_days(nowdate(), 3),
				"cloud_wms_source": SOURCE,
				"items": [
					{"item_code": code, "qty": qty, "rate": 10, "delivery_date": add_days(nowdate(), 3)}
					for code, qty in (lines or [(self.item, 3)])
				],
			}
		)
		doc.insert()
		doc.submit()
		frappe.db.commit()
		frappe.set_user(PICKER)
		return doc.name

	def key(self, name):
		return f"{PREFIX}{name}-{frappe.generate_hash(length=6)}"

	def call(self, fn, user=None, **kwargs):
		if user:
			frappe.set_user(user)
		if "idempotency_key" not in kwargs and fn not in (api.list_tasks, api.get):
			kwargs["idempotency_key"] = self.key(fn.__name__)
		return fn(**kwargs)

	def ok(self, response):
		self.assertNotIn("error", response, response)
		return response["data"]

	def err(self, response, code):
		self.assertIn("error", response, response)
		self.assertEqual(response["error"]["code"], code, response)

	def claim(self, order, user=PICKER, **kwargs):
		return self.ok(self.call(api.claim, user=user, sales_order=order, **kwargs))

	def scan_row(self, task, row=0, qty=None):
		line = task["lines"][row]
		pick = task["pick_list"]
		barcode = line["location_barcode"]
		self.ok(self.call(api.confirm_location, pick_list=pick, row=line["row"], barcode=barcode))
		return self.ok(
			self.call(
				api.confirm_pick,
				pick_list=pick,
				row=line["row"],
				item_barcode=line["item_code"],
				qty=qty or line["requested_qty"],
			)
		)

	def events(self, order, event_type):
		return frappe.get_all(
			"WMS Task Event", filters={"sales_order": order, "event_type": event_type}, pluck="name"
		)

	def test_claim_creates_a_draft_pick_list_assigned_to_the_picker(self):
		order = self.order()
		task = self.claim(order)

		self.assertEqual(task["status"], "claimed")
		self.assertEqual(task["sales_order"], order)
		self.assertEqual(task["assignees"], [PICKER])
		self.assertTrue(task["mine"])
		self.assertEqual(len(task["lines"]), 1)
		line = task["lines"][0]
		self.assertEqual((line["location"], line["location_barcode"]), (self.bin_a, BARCODE_A))
		self.assertEqual((line["requested_qty"], line["picked_qty"]), (3, 0))
		doc = frappe.get_doc("Pick List", task["pick_list"])
		self.assertEqual((doc.docstatus, doc.scan_mode, doc.pick_manually), (0, 1, 1))
		self.assertEqual(len(self.events(order, "Task Claimed")), 1)

	def test_claim_is_idempotent_and_exclusive(self):
		order = self.order()
		key = self.key("claim")
		first = self.call(api.claim, sales_order=order, idempotency_key=key)
		again = self.call(api.claim, sales_order=order, idempotency_key=key)
		self.assertTrue(again["replayed"])
		self.assertEqual(again["data"]["pick_list"], first["data"]["pick_list"])
		self.assertEqual(len(service.pick_lists_for_order(order)), 1)

		self.err(self.call(api.claim, user=OTHER_PICKER, sales_order=order), "CONFLICT")
		self.assertEqual(len(service.pick_lists_for_order(order)), 1)

	def test_only_supervisors_assign_tasks_to_others(self):
		order = self.order()
		self.err(self.call(api.claim, sales_order=order, assignee=OTHER_PICKER), "FORBIDDEN")
		self.err(self.call(api.claim, user=SUPERVISOR, sales_order=order, assignee=INTAKE), "INVALID_REQUEST")
		task = self.claim(order, user=SUPERVISOR, assignee=OTHER_PICKER)
		self.assertEqual(task["assignees"], [OTHER_PICKER])
		self.assertEqual(len(self.events(order, "Task Assigned")), 1)

	def test_roles_gate_the_endpoints(self):
		order = self.order()
		self.err(self.call(api.claim, user=INTAKE, sales_order=order), "FORBIDDEN")
		task = self.claim(order)
		self.err(self.call(api.complete, user=OTHER_PICKER, pick_list=task["pick_list"]), "FORBIDDEN")
		self.err(
			self.call(
				api.approve_shortage, user=PICKER, pick_list=task["pick_list"], row=task["lines"][0]["row"]
			),
			"FORBIDDEN",
		)

	def test_scanning_validates_location_item_and_quantity(self):
		order = self.order()
		task = self.claim(order)
		pick, row = task["pick_list"], task["lines"][0]["row"]

		self.err(
			self.call(api.confirm_pick, pick_list=pick, row=row, item_barcode=self.item),
			"LOCATION_NOT_CONFIRMED",
		)
		self.err(
			self.call(api.confirm_location, pick_list=pick, row=row, barcode=BARCODE_B), "WRONG_LOCATION"
		)
		self.ok(self.call(api.confirm_location, pick_list=pick, row=row, barcode=BARCODE_A.lower()))
		self.err(
			self.call(api.confirm_pick, pick_list=pick, row=row, item_barcode=self.item_2), "WRONG_ITEM"
		)
		self.err(
			self.call(api.confirm_pick, pick_list=pick, row=row, item_barcode=self.item, qty=4), "OVERPICK"
		)
		after = self.ok(
			self.call(api.confirm_pick, pick_list=pick, row=row, item_barcode=ITEM_BARCODE, qty=2)
		)
		self.assertEqual(after["status"], "picking")
		self.assertEqual(after["lines"][0]["picked_qty"], 2)
		self.assertEqual(len(self.events(order, "Pick Confirmed")), 1)

	def test_complete_submits_the_pick_list_and_reserves_stock(self):
		order = self.order()
		task = self.scan_row(self.claim(order))
		done = self.ok(self.call(api.complete, pick_list=task["pick_list"]))

		self.assertEqual((done["docstatus"], done["status"]), (1, "ready_to_dispatch"))
		reserved = frappe.db.get_value(
			"Stock Reservation Entry",
			{"voucher_no": order, "docstatus": 1},
			"reserved_qty",
		)
		self.assertEqual(reserved, 3)
		self.assertEqual(len(self.events(order, "Task Completed")), 1)
		self.assertNotIn(order, [row["sales_order"] for row in self.ok(self.call(api.list_tasks))["claimable"]])
		self.err(self.call(api.claim, user=OTHER_PICKER, sales_order=order), "CONFLICT")

	def test_complete_requires_everything_picked(self):
		task = self.scan_row(self.claim(self.order()), qty=1)
		self.err(self.call(api.complete, pick_list=task["pick_list"]), "NOT_FULLY_PICKED")

	def test_short_pick_needs_supervisor_approval_before_completion(self):
		order = self.order()
		task = self.scan_row(self.claim(order), qty=1)
		pick, row = task["pick_list"], task["lines"][0]["row"]

		self.err(self.call(api.record_shortage, pick_list=pick, row=row, reason=" "), "INVALID_REQUEST")
		short = self.ok(self.call(api.record_shortage, pick_list=pick, row=row, reason="Bin has 1 left"))
		self.assertEqual(short["status"], "qa_required")
		self.assertEqual(short["lines"][0]["shortage_state"], "Pending")
		self.err(self.call(api.complete, pick_list=pick), "QA_REQUIRED")
		self.err(self.call(api.confirm_pick, pick_list=pick, row=row, item_barcode=self.item), "QA_REQUIRED")

		approved = self.ok(self.call(api.approve_shortage, user=SUPERVISOR, pick_list=pick, row=row))
		self.assertEqual(approved["lines"][0]["requested_qty"], 1)
		self.assertEqual(approved["lines"][0]["shortage_state"], "Approved")
		self.assertEqual(approved["status"], "picking")
		self.assertEqual(len(self.events(order, "Short Pick")), 1)
		self.assertEqual(len(self.events(order, "Short Pick Approved")), 1)

		done = self.ok(self.call(api.complete, user=PICKER, pick_list=pick))
		self.assertEqual(done["status"], "ready_to_dispatch")
		self.assertEqual(
			frappe.db.get_value("Stock Reservation Entry", {"voucher_no": order, "docstatus": 1}, "reserved_qty"),
			1,
		)

	def test_approved_short_with_nothing_picked_removes_the_line_or_the_task(self):
		order = self.order([(self.item, 2), (self.item_2, 2)])
		task = self.claim(order)
		first = next(line for line in task["lines"] if line["item_code"] == self.item)
		pick = task["pick_list"]
		self.ok(self.call(api.confirm_location, pick_list=pick, row=first["row"], barcode=BARCODE_A))
		self.ok(self.call(api.record_shortage, pick_list=pick, row=first["row"], reason="Bin empty"))
		after = self.ok(self.call(api.approve_shortage, user=SUPERVISOR, pick_list=pick, row=first["row"]))
		self.assertEqual([line["item_code"] for line in after["lines"]], [self.item_2])

		second = after["lines"][0]
		self.ok(self.call(api.confirm_location, pick_list=pick, row=second["row"], barcode=BARCODE_B))
		self.ok(self.call(api.record_shortage, pick_list=pick, row=second["row"], reason="Bin empty"))
		gone = self.ok(self.call(api.approve_shortage, user=SUPERVISOR, pick_list=pick, row=second["row"]))
		self.assertEqual(gone["status"], "cancelled")
		self.assertFalse(frappe.db.exists("Pick List", pick))
		self.assertEqual(len(self.events(order, "Task Cancelled")), 1)
		self.assertIn(order, [row["sales_order"] for row in self.ok(self.call(api.list_tasks))["claimable"]])

	def test_release_returns_the_order_to_the_queue(self):
		order = self.order()
		task = self.claim(order)
		self.err(self.call(api.release, user=OTHER_PICKER, pick_list=task["pick_list"]), "FORBIDDEN")
		self.ok(self.call(api.release, user=PICKER, pick_list=task["pick_list"]))
		self.assertFalse(frappe.db.exists("Pick List", task["pick_list"]))
		self.assertEqual(len(self.events(order, "Task Released To Queue")), 1)
		self.assertIn(order, [row["sales_order"] for row in self.ok(self.call(api.list_tasks))["claimable"]])

	def test_a_picker_cannot_release_once_picking_started(self):
		task = self.scan_row(self.claim(self.order()), qty=1)
		self.err(self.call(api.release, pick_list=task["pick_list"]), "FORBIDDEN")
		self.ok(self.call(api.release, user=SUPERVISOR, pick_list=task["pick_list"]))

	def test_task_lists_show_each_picker_only_their_own_claims(self):
		order = self.order()
		listing = self.ok(self.call(api.list_tasks))
		claimable = {row["sales_order"]: row for row in listing["claimable"]}
		self.assertEqual(claimable[order]["remaining_qty"], 3)
		self.assertEqual(listing["active"], [])

		task = self.claim(order)
		self.assertNotIn(order, [row["sales_order"] for row in self.ok(self.call(api.list_tasks))["claimable"]])
		self.assertEqual([t["pick_list"] for t in self.ok(self.call(api.list_tasks))["active"]], [task["pick_list"]])
		self.assertEqual(self.ok(self.call(api.list_tasks, user=OTHER_PICKER))["active"], [])
		supervisor_view = self.ok(self.call(api.list_tasks, user=SUPERVISOR))["active"]
		self.assertIn(task["pick_list"], [t["pick_list"] for t in supervisor_view])


def install_fields():
	from cloud_wms.setup import install

	install.ensure_setup()
