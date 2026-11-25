import functools

import frappe

from cloud_wms.services import audit, errors, idempotency

WMS_ROLES = ("WMS Intake", "WMS Picker", "WMS Dispatch", "WMS Supervisor")


def wms_endpoint(operation, roles=(), idempotent=False):
	"""Wrap a service function in the WMS request/response contract.

	Apply ``@frappe.whitelist(methods=[...])`` *outside* this decorator. Idempotent endpoints must
	declare an ``idempotency_key`` parameter; it is excluded from the request hash.
	"""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			audit.reset_correlation_id()
			cid = audit.correlation_id()
			try:
				_require_roles(roles)
				if idempotent:
					key = kwargs.get("idempotency_key")
					payload = {k: v for k, v in kwargs.items() if k != "idempotency_key"}
					result, replayed = idempotency.run_idempotent(
						operation, key, payload, lambda: fn(*args, **kwargs)
					)
				else:
					result, replayed = fn(*args, **kwargs), False
			except Exception as exc:
				return _error_response(exc, cid, operation)
			return {"data": result, "correlation_id": cid, "replayed": replayed}

		return wrapper

	return decorator


def _require_roles(roles):
	if not roles:
		return
	if frappe.session.user == "Guest":
		raise errors.Forbidden("Authentication required.")
	allowed = set(roles) | {"System Manager"}
	if not allowed & set(frappe.get_roles()):
		raise errors.Forbidden("You do not have a WMS role that permits this action.")


def _error_response(exc, cid, operation):
	mapped = errors.from_exception(exc)
	if mapped is None:
		frappe.log_error(title=f"cloud_wms {operation} failed ({cid})")
		mapped = errors.WmsError(
			"Unexpected error. Quote the correlation id when reporting this.", code="INTERNAL_ERROR"
		)
	frappe.db.rollback()
	frappe.local.response["http_status_code"] = mapped.http_status
	return {"error": {**mapped.to_dict(), "correlation_id": cid}}
