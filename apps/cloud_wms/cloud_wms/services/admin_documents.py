"""Pick List and Delivery Note exception handling for WMS Admin and WMS Supervisor (admin screen 7).

Both documents are read-only here except for cancellation. ERPNext reverses what each document
posted: cancelling a Delivery Note reverses its stock ledger entries and the delivered quantities and
restores the stock reservations; cancelling a Pick List cancels its reservations and returns the
Sales Order to the pick queue. A Pick List with a submitted Delivery Note is never cancelled; the
Delivery Note goes first.
"""

import frappe
from frappe.utils import cstr

from cloud_wms.services import audit, tasks
from cloud_wms.services.admin import LIST_LIMIT, _check_modified, _require, _search
from cloud_wms.services.dispatch import _as_system
from cloud_wms.services.errors import Conflict

PICK_FIELDS = ["name", "status", "docstatus", "customer", "company", "owner", "creation", "modified"]
NOTE_FIELDS = [
	"name",
	"status",
	"docstatus",
	"customer",
	"customer_name",
	"company",
	"posting_date",
	"total_qty",
	"is_return",
	"owner",
	"creation",
	"modified",
]


# Pick Lists


def list_pick_lists(search=None, status=None):
	or_filters = _search(search, "name", "customer")
	if or_filters:
		matches = _parents_matching("Pick List Item", "sales_order", search)
		if matches:
			or_filters.append(["name", "in", matches])
	rows = frappe.get_all(
		"Pick List",
		filters={"purpose": "Delivery", **({"status": status} if status else {})},
		or_filters=or_filters,
		fields=PICK_FIELDS,
		order_by="creation desc",
		limit=LIST_LIMIT,
	)
	orders = _children_by_parent("Pick List Item", "sales_order", [row.name for row in rows])
	for row in rows:
		row["sales_orders"] = orders.get(row.name, [])
	return rows


def get_pick_list(name):
	_require("Pick List", name)
	pick = frappe.get_doc("Pick List", name)
	data = {field: pick.get(field) for field in PICK_FIELDS}
	data["assignees"] = tasks._assignees(name) if pick.docstatus == 0 else []
	data["sales_orders"] = tasks._orders_of(pick)
	data["lines"] = [
		{
			"row": line.idx,
			"item_code": line.item_code,
			"item_name": line.item_name,
			"warehouse": line.warehouse,
			"qty": line.qty,
			"picked_qty": line.picked_qty,
			"uom": line.stock_uom,
			"sales_order": line.sales_order,
			"shortage_state": line.get("cloud_wms_shortage_state"),
		}
		for line in pick.locations
	]
	data["delivery_notes"] = _notes_for_pick(name)
	data["cancel_blocker"] = _pick_blocker(pick, data["delivery_notes"])
	return data


def cancel_pick_list(pick_list, modified=None, reason=None):
	_require("Pick List", pick_list)
	_check_modified("Pick List", pick_list, modified)
	pick = tasks._load(pick_list, "cancel", for_update=True)
	blocker = _pick_blocker(pick, _notes_for_pick(pick.name))
	if blocker:
		raise Conflict(blocker["message"], code="IN_USE", next_action=blocker["next_action"])
	orders = tasks._orders_of(pick)
	pick.cancel()
	audit.record_event(
		"Task Cancelled",
		pick_list=pick.name,
		sales_order=orders[0] if orders else None,
		reason=_reason(reason),
		details={"sales_orders": orders, "via": "admin"},
	)
	return get_pick_list(pick.name)


def _pick_blocker(pick, notes):
	if pick.docstatus == 0:
		return {
			"message": f"Pick task {pick.name} is still open.",
			"next_action": "Release it from the Pick screen; an open task is not cancelled.",
		}
	if pick.docstatus == 2:
		return {"message": f"{pick.name} is already cancelled.", "next_action": None}
	submitted = [note["name"] for note in notes if note["docstatus"] == 1]
	if submitted:
		return {
			"message": f"Delivery Note {submitted[0]} is submitted for {pick.name}.",
			"next_action": "Cancel the Delivery Note first.",
		}
	return None


def _notes_for_pick(pick_list):
	names = frappe.get_all(
		"Delivery Note Item",
		filters={"against_pick_list": pick_list, "parenttype": "Delivery Note"},
		pluck="parent",
		distinct=True,
	)
	return _summaries("Delivery Note", names)


# Delivery Notes


def list_delivery_notes(search=None, status=None):
	or_filters = _search(search, "name", "customer", "customer_name")
	if or_filters:
		matches = _parents_matching("Delivery Note Item", "against_sales_order", search) + _parents_matching(
			"Delivery Note Item", "against_pick_list", search
		)
		if matches:
			or_filters.append(["name", "in", matches])
	rows = frappe.get_all(
		"Delivery Note",
		filters={"status": status} if status else None,
		or_filters=or_filters,
		fields=NOTE_FIELDS,
		order_by="creation desc",
		limit=LIST_LIMIT,
	)
	names = [row.name for row in rows]
	orders = _children_by_parent("Delivery Note Item", "against_sales_order", names)
	picks = _children_by_parent("Delivery Note Item", "against_pick_list", names)
	for row in rows:
		row["sales_orders"] = orders.get(row.name, [])
		row["pick_lists"] = picks.get(row.name, [])
	return rows


def get_delivery_note(name):
	_require("Delivery Note", name)
	note = frappe.get_doc("Delivery Note", name)
	data = {field: note.get(field) for field in NOTE_FIELDS}
	data["lines"] = [
		{
			"row": line.idx,
			"item_code": line.item_code,
			"item_name": line.item_name,
			"warehouse": line.warehouse,
			"qty": line.qty,
			"uom": line.uom,
			"sales_order": line.against_sales_order,
			"pick_list": line.against_pick_list,
		}
		for line in note.items
	]
	data["sales_orders"] = sorted(
		{line.against_sales_order for line in note.items if line.against_sales_order}
	)
	data["pick_lists"] = sorted({line.against_pick_list for line in note.items if line.against_pick_list})
	data["reference"] = note.get("lr_no")
	data["cancel_blocker"] = _note_blocker(note, data["sales_orders"])
	return data


def cancel_delivery_note(delivery_note, modified=None, reason=None):
	_require("Delivery Note", delivery_note)
	_check_modified("Delivery Note", delivery_note, modified)
	note = frappe.get_doc("Delivery Note", delivery_note, for_update=True)
	note.check_permission("cancel")
	orders = sorted({line.against_sales_order for line in note.items if line.against_sales_order})
	picks = sorted({line.against_pick_list for line in note.items if line.against_pick_list})
	blocker = _note_blocker(note, orders)
	if blocker:
		raise Conflict(blocker["message"], code="IN_USE", next_action=blocker["next_action"])
	# Reversing the ledger touches accounts, bins and reservations a supervisor cannot write; the
	# cancel permission was checked above, the same pattern dispatch uses for submit.
	with _as_system():
		note.cancel()
	audit.record_event(
		"Delivery Cancelled",
		delivery_note=note.name,
		sales_order=orders[0] if orders else None,
		pick_list=picks[0] if picks else None,
		reason=_reason(reason),
		details={"sales_orders": orders, "pick_lists": picks},
	)
	return get_delivery_note(note.name)


def _note_blocker(note, orders):
	if note.docstatus != 1:
		state = "cancelled" if note.docstatus == 2 else "a draft"
		return {"message": f"{note.name} is {state}.", "next_action": None}
	for order in orders:
		status = frappe.db.get_value("Sales Order", order, "status")
		if status in ("On Hold", "Closed"):
			return {
				"message": f"Sales Order {order} is {status}.",
				"next_action": "Reopen it in ERPNext first.",
			}
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"delivery_note": note.name, "docstatus": 1, "parenttype": "Sales Invoice"},
		pluck="parent",
		distinct=True,
	)
	if invoices:
		return {
			"message": f"Sales Invoice {invoices[0]} is submitted against {note.name}.",
			"next_action": "Cancel the invoice in ERPNext first.",
		}
	returns = frappe.get_all(
		"Delivery Note", filters={"return_against": note.name, "docstatus": 1}, pluck="name"
	)
	if returns:
		return {
			"message": f"Return {returns[0]} is submitted against {note.name}.",
			"next_action": "Cancel the return first.",
		}
	return None


# Helpers


def _summaries(doctype, names):
	if not names:
		return []
	return frappe.get_all(
		doctype,
		filters={"name": ["in", names]},
		fields=["name", "docstatus", "status"],
		order_by="creation asc",
	)


def _parents_matching(child, field, search):
	return frappe.get_all(
		child,
		filters={field: ["like", f"%{cstr(search).strip()}%"]},
		pluck="parent",
		distinct=True,
		limit=LIST_LIMIT,
	)


def _children_by_parent(child, field, parents):
	if not parents:
		return {}
	result = {}
	for row in frappe.get_all(
		child,
		filters={"parent": ["in", parents], field: ["is", "set"]},
		fields=["parent", field],
		distinct=True,
	):
		values = result.setdefault(row.parent, [])
		if row[field] not in values:
			values.append(row[field])
	return {parent: sorted(values) for parent, values in result.items()}


def _reason(reason):
	return cstr(reason).strip()[:500] or None
