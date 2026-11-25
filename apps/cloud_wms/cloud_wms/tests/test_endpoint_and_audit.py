import frappe
from frappe.tests import IntegrationTestCase

from cloud_wms.api import session
from cloud_wms.services import audit, errors
from cloud_wms.services.endpoint import WMS_ROLES, wms_endpoint


@wms_endpoint("test.guarded", roles=("WMS Picker",))
def _guarded():
	return {"ok": True}


@wms_endpoint("test.validation")
def _failing():
	frappe.throw("Bad input", frappe.ValidationError)


@wms_endpoint("test.crash")
def _crashing():
	raise RuntimeError("secret internals")


class TestEndpoint(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_success_envelope(self):
		frappe.set_user("Administrator")
		response = _guarded()
		self.assertEqual(response["data"], {"ok": True})
		self.assertFalse(response["replayed"])
		self.assertTrue(response["correlation_id"])

	def test_guest_is_forbidden_with_http_403(self):
		frappe.set_user("Guest")
		response = _guarded()
		self.assertEqual(response["error"]["code"], "FORBIDDEN")
		self.assertEqual(frappe.local.response["http_status_code"], 403)

	def test_validation_error_maps_to_422_with_message(self):
		frappe.set_user("Administrator")
		response = _failing()
		self.assertEqual(response["error"]["code"], "VALIDATION_FAILED")
		self.assertIn("Bad input", response["error"]["message"])
		self.assertEqual(frappe.local.response["http_status_code"], 422)

	def test_unexpected_error_hides_internals(self):
		frappe.set_user("Administrator")
		response = _crashing()
		self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
		self.assertNotIn("secret", response["error"]["message"])
		self.assertEqual(frappe.local.response["http_status_code"], 500)

	def test_session_context_lists_wms_roles(self):
		frappe.set_user("Administrator")
		data = session.context()["data"]
		self.assertEqual(data["user"], "Administrator")
		self.assertEqual(set(data["roles"]), set(WMS_ROLES))


class TestAudit(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_event_records_actor_and_correlation(self):
		event = audit.record_event("Task Claimed", pick_list="PICK-1", details={"b": 1, "a": 2})
		event.reload()
		self.assertEqual(event.actor, "Administrator")
		self.assertTrue(event.correlation_id)
		self.assertEqual(event.details, '{"a": 2, "b": 1}')

	def test_events_are_immutable(self):
		event = audit.record_event("Task Claimed", pick_list="PICK-1")
		event.reason = "tampered"
		with self.assertRaises(frappe.PermissionError):
			event.save()
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("WMS Task Event", event.name, force=True)

	def test_mapped_errors_have_stable_codes(self):
		self.assertEqual(errors.from_exception(frappe.DoesNotExistError()).code, "NOT_FOUND")
		self.assertEqual(errors.from_exception(frappe.PermissionError()).http_status, 403)
		self.assertIsNone(errors.from_exception(RuntimeError()))
