import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from cloud_wms.services import errors, idempotency

PREFIX = "test-cwms-"


class TestIdempotency(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete("WMS Request", {"idempotency_key": ["like", f"{PREFIX}%"]})
		frappe.db.commit()

	def run_op(self, key, payload, fn, operation="test.op"):
		return idempotency.run_idempotent(operation, key, payload, fn)

	def test_replays_stored_response_without_rerunning(self):
		calls = []

		def fn():
			calls.append(1)
			return {"value": len(calls)}

		key = f"{PREFIX}replay-1"
		first = self.run_op(key, {"a": 1}, fn)
		second = self.run_op(key, {"a": 1}, fn)

		self.assertEqual(first, ({"value": 1}, False))
		self.assertEqual(second, ({"value": 1}, True))
		self.assertEqual(len(calls), 1)

	def test_same_key_with_different_payload_or_operation_conflicts(self):
		key = f"{PREFIX}conflict-1"
		self.run_op(key, {"a": 1}, lambda: {})

		with self.assertRaises(errors.Conflict) as ctx:
			self.run_op(key, {"a": 2}, lambda: {})
		self.assertEqual(ctx.exception.code, "IDEMPOTENCY_CONFLICT")

		with self.assertRaises(errors.Conflict):
			self.run_op(key, {"a": 1}, lambda: {}, operation="other.op")

	def test_business_failure_is_recorded_and_replayed(self):
		key = f"{PREFIX}failure-1"
		calls = []

		def fn():
			calls.append(1)
			frappe.throw("Not enough stock", frappe.ValidationError)

		with self.assertRaises(errors.ValidationFailed) as first:
			self.run_op(key, {}, fn)
		with self.assertRaises(errors.WmsError) as second:
			self.run_op(key, {}, fn)

		self.assertEqual(len(calls), 1)
		self.assertIn("Not enough stock", first.exception.message)
		self.assertEqual(second.exception.code, "VALIDATION_FAILED")
		self.assertEqual(second.exception.http_status, 422)
		self.assertEqual(frappe.db.get_value("WMS Request", {"idempotency_key": key}, "status"), "Failed")

	def test_unexpected_error_leaves_no_record_so_retry_runs(self):
		key = f"{PREFIX}crash-1"

		def boom():
			raise RuntimeError("boom")

		with self.assertRaises(RuntimeError):
			self.run_op(key, {}, boom)
		self.assertFalse(frappe.db.exists("WMS Request", {"idempotency_key": key}))

		self.assertEqual(self.run_op(key, {}, lambda: {"ok": True}), ({"ok": True}, False))

	def test_business_changes_roll_back_on_failure(self):
		key = f"{PREFIX}rollback-1"

		def fn():
			frappe.get_doc({"doctype": "Note", "title": f"{PREFIX}rollback", "content": "x"}).insert()
			frappe.throw("nope", frappe.ValidationError)

		with self.assertRaises(errors.ValidationFailed):
			self.run_op(key, {}, fn)
		self.assertFalse(frappe.db.exists("Note", {"title": f"{PREFIX}rollback"}))

	def test_in_progress_request_is_rejected_until_stale(self):
		key = f"{PREFIX}progress-1"
		digest = idempotency.payload_hash({})
		doc = frappe.get_doc(
			{
				"doctype": "WMS Request",
				"idempotency_key": key,
				"operation": "test.op",
				"user": "Administrator",
				"request_hash": digest,
				"status": "Processing",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

		with self.assertRaises(errors.Conflict) as ctx:
			self.run_op(key, {}, lambda: {})
		self.assertEqual(ctx.exception.code, "REQUEST_IN_PROGRESS")

		stale = add_to_date(now_datetime(), minutes=-(idempotency.STALE_AFTER_MINUTES + 1))
		frappe.db.set_value("WMS Request", doc.name, "modified", stale, update_modified=False)
		frappe.db.commit()

		self.assertEqual(self.run_op(key, {}, lambda: {"took": "over"}), ({"took": "over"}, False))

	def test_invalid_keys_are_rejected(self):
		for key in (None, "", "short", "has space in it", "x" * 129):
			with self.assertRaises(errors.InvalidRequest, msg=repr(key)):
				self.run_op(key, {}, lambda: {})
