import hashlib
import json
import re

import frappe
from frappe.utils import add_to_date, now_datetime

from cloud_wms.services import errors

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{8,128}$")
STALE_AFTER_MINUTES = 10


def validate_key(key):
	if not isinstance(key, str) or not KEY_PATTERN.match(key):
		raise errors.InvalidRequest(
			"idempotency_key is required: 8-128 characters of letters, digits and _-:.",
			code="INVALID_IDEMPOTENCY_KEY",
		)


def payload_hash(payload):
	canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
	return hashlib.sha256(canonical.encode()).hexdigest()


def run_idempotent(operation, key, payload, fn):
	"""Run ``fn()`` at most once per idempotency key.

	Returns ``(result, replayed)``. ``fn`` must return a JSON-serialisable value and must not commit.
	The request row is committed before ``fn`` runs, so concurrent duplicates are serialised by the
	unique index. On success the stored response commits atomically with the business changes.
	"""
	validate_key(key)
	digest = payload_hash(payload)
	user = frappe.session.user

	existing = _claim(operation, key, digest, user)
	if existing is not None:
		return _replay(existing, operation, digest, user)

	try:
		result = fn()
	except Exception as exc:
		frappe.db.rollback()
		mapped = errors.from_exception(exc)
		if mapped is None:
			frappe.db.delete("WMS Request", {"idempotency_key": key})
			frappe.db.commit()
			raise
		_finish(key, "Failed", response=mapped.to_dict(), error_code=mapped.code)
		frappe.db.commit()
		raise mapped from exc

	_finish(key, "Succeeded", response=result)
	frappe.db.commit()
	return result, False


def _claim(operation, key, digest, user):
	"""Insert the processing row. Returns None if claimed, else the existing row."""
	try:
		frappe.get_doc(
			{
				"doctype": "WMS Request",
				"idempotency_key": key,
				"operation": operation,
				"user": user,
				"request_hash": digest,
				"status": "Processing",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return None
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback()

	row = frappe.db.get_value(
		"WMS Request",
		{"idempotency_key": key},
		["name", "operation", "user", "request_hash", "status", "response_json", "modified"],
		as_dict=True,
		for_update=True,
	)
	if row is None:
		raise errors.Conflict("Request is being finalised; retry.", code="REQUEST_IN_PROGRESS")
	if row.status == "Processing" and _is_stale(row) and _same_request(row, operation, digest, user):
		frappe.db.set_value("WMS Request", row.name, "status", "Processing")
		frappe.db.commit()
		return None
	frappe.db.commit()
	return row


def _is_stale(row):
	return row.modified < add_to_date(now_datetime(), minutes=-STALE_AFTER_MINUTES)


def _same_request(row, operation, digest, user):
	return row.operation == operation and row.request_hash == digest and row.user == user


def _replay(row, operation, digest, user):
	if not _same_request(row, operation, digest, user):
		raise errors.Conflict(
			"This idempotency key was already used for a different request.",
			code="IDEMPOTENCY_CONFLICT",
		)
	if row.status == "Processing":
		raise errors.Conflict("The original request is still processing.", code="REQUEST_IN_PROGRESS")
	stored = json.loads(row.response_json) if row.response_json else None
	if row.status == "Failed":
		error = errors.WmsError(stored["message"], code=stored["code"], next_action=stored.get("next_action"))
		error.http_status = _status_for(stored["code"])
		raise error
	return stored, True


def _status_for(code):
	for cls in (
		errors.InvalidRequest,
		errors.Forbidden,
		errors.NotFound,
		errors.Conflict,
		errors.ValidationFailed,
	):
		if cls.code == code:
			return cls.http_status
	return 409 if code in {"DUPLICATE"} else 422


def _finish(key, status, response, error_code=None):
	name = frappe.db.get_value("WMS Request", {"idempotency_key": key}, "name")
	frappe.db.set_value(
		"WMS Request",
		name,
		{
			"status": status,
			"response_json": json.dumps(response, default=str),
			"error_code": error_code,
		},
	)
