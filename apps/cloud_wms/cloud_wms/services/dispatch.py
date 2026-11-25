"""Dispatch: turn a submitted Pick List into a submitted Delivery Note.

ERPNext's own ``create_delivery_note`` maps the picked quantities (not the ordered ones), so a
supervisor-approved short pick delivers exactly what was picked. The Delivery Note is created and
submitted as the session user; the stock ledger posts on submission.
"""

import contextlib

import frappe

from cloud_wms.services import audit, tasks
from cloud_wms.services.errors import Conflict, InvalidRequest, ValidationFailed

MAX_REFERENCE_LENGTH = 140


def confirm(pick_list, reference=None):
	reference = _clean_reference(reference)
	pick = tasks._load(pick_list, "read", for_update=True)
	if pick.docstatus != 1:
		raise Conflict(
			f"Pick List {pick.name} has not been submitted; finish picking first.", code="NOT_READY"
		)
	orders = tasks._orders_of(pick)

	note = _existing_note(pick.name)
	if note and note.docstatus == 1:
		return _result(pick, note, orders, already_dispatched=True)
	if not note:
		note = _create_note(pick)
		audit.record_event(
			"Delivery Created", sales_order=_first(orders), pick_list=pick.name, details={"delivery_note": note.name}
		)
	if reference:
		note.lr_no = reference
	with _as_system():
		note.submit()

	note = frappe.get_doc("Delivery Note", note.name)
	audit.record_event(
		"Delivery Submitted",
		sales_order=_first(orders),
		pick_list=pick.name,
		details={"delivery_note": note.name, "reference": reference},
	)
	return _result(pick, note, orders)


@contextlib.contextmanager
def _as_system():
	# Mapping and validating a Delivery Note reads customer, address and tax masters a Dispatch
	# user cannot read. The endpoint has already checked the role; the note's owner stays the user.
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


def _clean_reference(reference):
	reference = (str(reference).strip() if reference else "")
	if len(reference) > MAX_REFERENCE_LENGTH:
		raise InvalidRequest(f"The dispatch reference may be at most {MAX_REFERENCE_LENGTH} characters.")
	return reference


def _existing_note(pick_list):
	names = frappe.db.sql(
		"""
		select distinct dn.name
		from `tabDelivery Note` dn
		join `tabDelivery Note Item` dni on dni.parent = dn.name and dni.parenttype = 'Delivery Note'
		where dn.docstatus < 2 and dni.against_pick_list = %s
		order by dn.docstatus desc, dn.creation asc
		""",
		(pick_list,),
	)
	return frappe.get_doc("Delivery Note", names[0][0], for_update=True) if names else None


def _create_note(pick):
	from erpnext.stock.doctype.pick_list.pick_list import create_delivery_note

	user = frappe.session.user
	with _as_system():
		created = create_delivery_note(pick.name)
		if created and created.get("name"):
			frappe.db.set_value("Delivery Note", created.name, "owner", user, update_modified=False)
	if not created or not created.get("name"):
		raise ValidationFailed("Nothing picked in this Pick List is left to deliver.")
	# Reload so submission runs the ordinary mandatory-field checks.
	return frappe.get_doc("Delivery Note", created.name, for_update=True)


def _result(pick, note, orders, already_dispatched=False):
	pick.reload()
	return {
		"pick_list": pick.name,
		"sales_order": _first(orders),
		"pick_list_status": pick.status,
		"already_dispatched": already_dispatched,
		"delivery_note": {
			"name": note.name,
			"docstatus": note.docstatus,
			"status": note.status,
			"posting_date": str(note.posting_date),
			"posting_time": str(note.posting_time),
			"reference": note.lr_no or None,
			"units": sum(item.qty for item in note.items),
		},
	}


def _first(orders):
	return orders[0] if orders else None
