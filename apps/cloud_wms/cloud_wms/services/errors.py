import frappe


class WmsError(Exception):
	code = "INTERNAL_ERROR"
	http_status = 500

	def __init__(self, message, code=None, next_action=None):
		super().__init__(message)
		self.message = message
		if code:
			self.code = code
		self.next_action = next_action

	def to_dict(self):
		return {"code": self.code, "message": self.message, "next_action": self.next_action}


class InvalidRequest(WmsError):
	code = "INVALID_REQUEST"
	http_status = 400


class Forbidden(WmsError):
	code = "FORBIDDEN"
	http_status = 403


class NotFound(WmsError):
	code = "NOT_FOUND"
	http_status = 404


class Conflict(WmsError):
	code = "CONFLICT"
	http_status = 409


class ValidationFailed(WmsError):
	code = "VALIDATION_FAILED"
	http_status = 422


def _message_log_text():
	messages = []
	for entry in frappe.local.message_log or []:
		raw = entry.get("message") if isinstance(entry, dict) else entry
		if raw:
			messages.append(frappe.utils.strip_html_tags(str(raw)))
	frappe.local.message_log = []
	return " ".join(messages)


def from_exception(exc):
	"""Map a Frappe/ERPNext exception to a WmsError, or None if it is unexpected."""
	if isinstance(exc, WmsError):
		return exc
	if isinstance(exc, frappe.PermissionError):
		return Forbidden("You are not permitted to perform this action.")
	if isinstance(exc, frappe.DoesNotExistError):
		return NotFound(str(exc) or "The requested record does not exist.")
	if isinstance(exc, frappe.DuplicateEntryError):
		return Conflict("A record with the same identity already exists.", code="DUPLICATE")
	if isinstance(exc, frappe.UniqueValidationError):
		return Conflict(_message_log_text() or "A field that must be unique is already in use.", code="DUPLICATE")
	if isinstance(exc, frappe.ValidationError):
		return ValidationFailed(_message_log_text() or str(exc) or "Validation failed.")
	return None
