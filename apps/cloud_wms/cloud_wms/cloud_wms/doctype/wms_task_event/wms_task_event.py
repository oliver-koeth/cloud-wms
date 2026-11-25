import frappe
from frappe import _
from frappe.model.document import Document


class WMSTaskEvent(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw(_("WMS Task Events are immutable."), frappe.PermissionError)

	def on_trash(self):
		if not frappe.flags.in_uninstall:
			frappe.throw(_("WMS Task Events cannot be deleted."), frappe.PermissionError)
