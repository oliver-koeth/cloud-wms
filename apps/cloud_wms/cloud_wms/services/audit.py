import json
import uuid

import frappe

CORRELATION_HEADER = "X-Correlation-ID"
_VALID_CORRELATION = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:.")


def correlation_id():
	value = getattr(frappe.local, "cloud_wms_correlation_id", None)
	if not value:
		value = _from_header() or uuid.uuid4().hex
		frappe.local.cloud_wms_correlation_id = value
	return value


def _from_header():
	request = getattr(frappe.local, "request", None)
	value = request.headers.get(CORRELATION_HEADER) if request else None
	if value and len(value) <= 64 and set(value) <= _VALID_CORRELATION:
		return value
	return None


def reset_correlation_id():
	frappe.local.cloud_wms_correlation_id = None


def record_event(event_type, *, idempotency_key=None, details=None, **fields):
	"""Append an immutable WMS Task Event. Participates in the caller's transaction."""
	doc = frappe.get_doc(
		{
			"doctype": "WMS Task Event",
			"event_type": event_type,
			"actor": frappe.session.user,
			"correlation_id": correlation_id(),
			"idempotency_key": idempotency_key,
			"details": json.dumps(details, default=str, sort_keys=True) if details else None,
			**fields,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc
