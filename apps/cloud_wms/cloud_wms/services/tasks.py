"""Pick tasks, backed by ERPNext Pick Lists.

A task is a Sales Order that is claimable, then a draft Pick List while it is being picked. Every
change runs as the session user through ERPNext's own permission checks. Scan progress and shortage
approval live on custom fields of the Pick List Item rows.
"""

import frappe
from frappe.utils import flt

from cloud_wms.services import audit
from cloud_wms.services.errors import Conflict, Forbidden, InvalidRequest, NotFound, ValidationFailed

LIST_LIMIT = 100
CLAIMABLE_STATUSES = ("To Deliver and Bill", "To Deliver")
PRIVILEGED_ROLES = {"WMS Supervisor", "WMS Dispatch", "System Manager"}
SUPERVISOR_ROLES = {"WMS Supervisor", "System Manager"}
TERMINAL_STATUSES = ("Completed", "Cancelled")


def pick_lists_for_order(sales_order, active_only=False):
	"""Pick Lists (newest last) that pick from a Sales Order; Pick List rows hold the link."""
	rows = frappe.db.sql(
		"""
		select pl.name, pl.docstatus, pl.status
		from `tabPick List` pl
		where pl.docstatus < 2
			and exists (
				select 1 from `tabPick List Item` pli
				where pli.parent = pl.name and pli.parenttype = 'Pick List' and pli.sales_order = %s
			)
		order by pl.creation asc
		""",
		(sales_order,),
		as_dict=True,
	)
	if active_only:
		rows = [row for row in rows if _is_active(row.docstatus, row.status)]
	return rows


def _is_active(docstatus, status):
	return docstatus == 0 or (docstatus == 1 and status not in TERMINAL_STATUSES)


def list_tasks():
	return {"claimable": _claimable_orders(), "active": _active_tasks()}


def get_task(pick_list=None, sales_order=None):
	if pick_list:
		return _task_json(_load(pick_list, "read"))
	if sales_order:
		frappe.has_permission("Sales Order", "read", sales_order, throw=True)
		active = pick_lists_for_order(sales_order, active_only=True)
		if active:
			return _task_json(_load(active[-1].name, "read"))
		return _order_json(sales_order)
	raise InvalidRequest("pick_list or sales_order is required.")


def claim(sales_order, assignee=None):
	user = frappe.session.user
	assignee = assignee or user
	if assignee != user:
		if not _has_role(SUPERVISOR_ROLES):
			raise Forbidden("Only a supervisor can assign a task to someone else.")
		if not _is_picker(assignee):
			raise InvalidRequest(f"{assignee} is not an enabled user with the WMS Picker role.")

	if not frappe.db.exists("Sales Order", sales_order):
		raise NotFound(f"Sales Order {sales_order} does not exist.")
	order = frappe.get_doc("Sales Order", sales_order, for_update=True)
	order.check_permission("read")
	if order.docstatus != 1 or order.status not in CLAIMABLE_STATUSES:
		raise Conflict(f"Sales Order {sales_order} is not open for picking (status: {order.status}).")

	active = pick_lists_for_order(sales_order, active_only=True)
	if active:
		raise Conflict(
			f"Sales Order {sales_order} is already claimed by {_assignee_label(active[-1].name)}.",
			next_action="Refresh the task list.",
		)

	from erpnext.selling.doctype.sales_order.sales_order import create_pick_list

	pick = create_pick_list(sales_order)
	if not pick.locations:
		raise Conflict(f"Sales Order {sales_order} has nothing left to pick.")
	pick.scan_mode = 1
	pick.pick_manually = 1
	pick.insert()

	from frappe.desk.form.assign_to import add as assign

	assign(
		{
			"doctype": "Pick List",
			"name": pick.name,
			"assign_to": [assignee],
			"description": f"Pick {sales_order}",
			"notify": 0,
		}
	)

	audit.record_event("Task Claimed", sales_order=sales_order, pick_list=pick.name, details={"assignee": assignee})
	if assignee != user:
		audit.record_event(
			"Task Assigned", sales_order=sales_order, pick_list=pick.name, details={"assignee": assignee}
		)
	return _task_json(_load(pick.name, "read"))


def release(pick_list):
	pick = _load_draft(pick_list)
	picked = any(flt(row.picked_qty) or row.cloud_wms_location_confirmed for row in pick.locations)
	if picked and not _has_role(SUPERVISOR_ROLES):
		raise Forbidden("Picking has started; ask a supervisor to release this task.")

	sales_orders = _orders_of(pick)
	pick.check_permission("delete")
	frappe.delete_doc("Pick List", pick.name)
	audit.record_event(
		"Task Released To Queue",
		sales_order=sales_orders[0] if sales_orders else None,
		pick_list=pick.name,
		details={"discarded_scans": picked},
	)
	return {"pick_list": pick.name, "released": True}


def confirm_location(pick_list, row, barcode):
	pick = _load_draft(pick_list)
	line = _row(pick, row)
	scanned = _clean_scan(barcode)
	_ensure_no_pending_shortage(line)

	expected = {line.warehouse.casefold()}
	location_barcode = frappe.db.get_value("Warehouse", line.warehouse, "cloud_wms_location_barcode")
	if location_barcode:
		expected.add(location_barcode.casefold())
	if scanned.casefold() not in expected:
		raise ValidationFailed(
			f"Wrong location. Go to {location_barcode or line.warehouse} for {line.item_code}.",
			code="WRONG_LOCATION",
		)

	line.cloud_wms_location_confirmed = 1
	pick.save()
	audit.record_event(
		"Location Scanned",
		sales_order=line.sales_order,
		pick_list=pick.name,
		pick_list_item=line.name,
		warehouse=line.warehouse,
		scanned_value=scanned,
	)
	return _task_json(pick)


def confirm_pick(pick_list, row, item_barcode, qty=1):
	pick = _load_draft(pick_list)
	line = _row(pick, row)
	scanned = _clean_scan(item_barcode)
	qty = _positive_qty(qty)
	if not line.cloud_wms_location_confirmed:
		raise ValidationFailed("Scan the location before picking.", code="LOCATION_NOT_CONFIRMED")
	_ensure_no_pending_shortage(line)
	if not _matches_item(line.item_code, scanned):
		raise ValidationFailed(f"Wrong item. Expected {line.item_code}.", code="WRONG_ITEM")
	if flt(line.picked_qty) + qty > flt(line.stock_qty):
		raise ValidationFailed(
			f"Only {flt(line.stock_qty) - flt(line.picked_qty):g} left to pick for {line.item_code}.",
			code="OVERPICK",
		)

	line.picked_qty = flt(line.picked_qty) + qty
	pick.save()
	audit.record_event(
		"Pick Confirmed",
		sales_order=line.sales_order,
		pick_list=pick.name,
		pick_list_item=line.name,
		item_code=line.item_code,
		warehouse=line.warehouse,
		scanned_value=scanned,
		qty=qty,
	)
	return _task_json(pick)


def record_shortage(pick_list, row, reason):
	pick = _load_draft(pick_list)
	line = _row(pick, row)
	reason = (reason or "").strip()
	if not reason:
		raise InvalidRequest("A reason is required for a short pick.")
	if not line.cloud_wms_location_confirmed:
		raise ValidationFailed("Scan the location before reporting a shortage.", code="LOCATION_NOT_CONFIRMED")
	_ensure_no_pending_shortage(line)
	missing = flt(line.stock_qty) - flt(line.picked_qty)
	if missing <= 0:
		raise ValidationFailed("This line is already fully picked.", code="NOTHING_MISSING")

	line.cloud_wms_shortage_state = "Pending"
	line.cloud_wms_shortage_reason = reason
	pick.save()
	audit.record_event(
		"Short Pick",
		sales_order=line.sales_order,
		pick_list=pick.name,
		pick_list_item=line.name,
		item_code=line.item_code,
		warehouse=line.warehouse,
		qty=missing,
		reason=reason,
	)
	return _task_json(pick)


def approve_shortage(pick_list, row):
	pick = _load_draft(pick_list, assignee_only=False)
	line = _row(pick, row)
	if line.cloud_wms_shortage_state != "Pending":
		raise Conflict("This line has no shortage waiting for approval.")

	picked = flt(line.picked_qty)
	missing = flt(line.stock_qty) - picked
	reason = line.cloud_wms_shortage_reason
	sales_order = line.sales_order
	item_code = line.item_code
	warehouse = line.warehouse

	if picked > 0:
		line.qty = picked / (flt(line.conversion_factor) or 1)
		line.stock_qty = picked
		line.cloud_wms_shortage_state = "Approved"
	else:
		pick.remove(line)

	audit.record_event(
		"Short Pick Approved",
		sales_order=sales_order,
		pick_list=pick.name,
		pick_list_item=row,
		item_code=item_code,
		warehouse=warehouse,
		qty=missing,
		reason=reason,
		details={"picked": picked},
	)
	if not pick.locations:
		pick.check_permission("delete")
		frappe.delete_doc("Pick List", pick.name)
		audit.record_event(
			"Task Cancelled",
			sales_order=sales_order,
			pick_list=pick.name,
			reason="Every line was short with nothing picked.",
		)
		return {"pick_list": pick.name, "status": "cancelled", "lines": []}

	pick.save()
	return _task_json(pick)


def complete(pick_list):
	pick = _load_draft(pick_list)
	if not pick.locations:
		raise ValidationFailed("There is nothing to complete.")
	for line in pick.locations:
		if line.cloud_wms_shortage_state == "Pending":
			raise ValidationFailed(
				f"{line.item_code} has a shortage waiting for supervisor approval.", code="QA_REQUIRED"
			)
		if flt(line.picked_qty) < flt(line.stock_qty):
			raise ValidationFailed(
				f"{line.item_code} is not fully picked. Pick it or report a shortage.", code="NOT_FULLY_PICKED"
			)

	pick.submit()
	if frappe.db.get_single_value("Stock Settings", "enable_stock_reservation"):
		pick.reload()
		_reserve_as_system(pick)

	orders = _orders_of(pick)
	audit.record_event(
		"Task Completed",
		sales_order=orders[0] if orders else None,
		pick_list=pick.name,
		details={"lines": len(pick.locations)},
	)
	return _task_json(_load(pick.name, "read"))


def _reserve_as_system(pick):
	# Roles were checked at the endpoint; reservation spans doctypes the picker cannot write.
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		pick.create_stock_reservation_entries(notify=False)
	finally:
		frappe.set_user(user)


def _claimable_orders():
	orders = frappe.get_list(
		"Sales Order",
		filters={"docstatus": 1, "status": ["in", CLAIMABLE_STATUSES]},
		fields=["name", "customer", "delivery_date", "company", "set_warehouse"],
		order_by="delivery_date asc, creation asc",
		limit=LIST_LIMIT * 2,
	)
	if not orders:
		return []
	names = [order.name for order in orders]
	remaining = _remaining_qty(names)
	claimed = _orders_with_active_pick_list(names)
	return [
		_order_summary(order, remaining[order.name])
		for order in orders
		if remaining.get(order.name) and order.name not in claimed
	][:LIST_LIMIT]


def _remaining_qty(order_names):
	rows = frappe.db.sql(
		"""
		select parent, sum(qty - greatest(picked_qty / greatest(conversion_factor, 0.000001), delivered_qty)) as remaining,
			count(*) as line_count
		from `tabSales Order Item`
		where parent in %(names)s and delivered_by_supplier = 0
			and qty - greatest(picked_qty / greatest(conversion_factor, 0.000001), delivered_qty) > 0
		group by parent
		""",
		{"names": tuple(order_names)},
		as_dict=True,
	)
	return {row.parent: {"qty": flt(row.remaining), "lines": row.line_count} for row in rows}


def _orders_with_active_pick_list(order_names):
	rows = frappe.db.sql(
		"""
		select distinct pli.sales_order
		from `tabPick List Item` pli
		join `tabPick List` pl on pl.name = pli.parent
		where pli.parenttype = 'Pick List' and pli.sales_order in %(names)s
			and (pl.docstatus = 0 or (pl.docstatus = 1 and pl.status not in %(terminal)s))
		""",
		{"names": tuple(order_names), "terminal": TERMINAL_STATUSES},
	)
	return {row[0] for row in rows}


def _active_tasks():
	filters = {"docstatus": ["<", 2], "status": ["not in", TERMINAL_STATUSES]}
	if not _has_role(PRIVILEGED_ROLES):
		mine = _assigned_to(frappe.session.user)
		if not mine:
			return []
		filters["name"] = ["in", mine]
		filters["docstatus"] = 0
	names = frappe.get_list(
		"Pick List", filters=filters, pluck="name", order_by="creation asc", limit=LIST_LIMIT
	)
	return [_task_json(frappe.get_doc("Pick List", name)) for name in names]


def _assigned_to(user):
	return frappe.get_all(
		"ToDo",
		filters={"reference_type": "Pick List", "allocated_to": user, "status": "Open"},
		pluck="reference_name",
	)


def _assignees(pick_list):
	return frappe.get_all(
		"ToDo",
		filters={"reference_type": "Pick List", "reference_name": pick_list, "status": "Open"},
		pluck="allocated_to",
	)


def _assignee_label(pick_list):
	return ", ".join(_assignees(pick_list)) or "someone else"


def _order_summary(order, remaining):
	return {
		"sales_order": order.name,
		"customer": order.customer,
		"delivery_date": str(order.delivery_date) if order.delivery_date else None,
		"warehouse": order.set_warehouse,
		"status": "available",
		"remaining_qty": remaining["qty"],
		"lines": remaining["lines"],
	}


def _order_json(sales_order):
	order = frappe.db.get_value(
		"Sales Order", sales_order, ["name", "customer", "delivery_date", "set_warehouse"], as_dict=True
	)
	if not order:
		raise NotFound(f"Sales Order {sales_order} does not exist.")
	remaining = _remaining_qty([sales_order]).get(sales_order, {"qty": 0, "lines": 0})
	return _order_summary(order, remaining)


def _task_json(pick):
	orders = _orders_of(pick)
	lines = []
	for line in pick.locations:
		lines.append(
			{
				"row": line.name,
				"item_code": line.item_code,
				"item_name": line.item_name,
				"location": line.warehouse,
				"location_barcode": frappe.db.get_value(
					"Warehouse", line.warehouse, "cloud_wms_location_barcode"
				),
				"uom": line.stock_uom,
				"requested_qty": flt(line.stock_qty),
				"picked_qty": flt(line.picked_qty),
				"location_confirmed": bool(line.cloud_wms_location_confirmed),
				"shortage_state": line.cloud_wms_shortage_state or None,
				"shortage_reason": line.cloud_wms_shortage_reason or None,
			}
		)
	assignees = _assignees(pick.name)
	return {
		"pick_list": pick.name,
		"sales_order": orders[0] if orders else None,
		"customer": pick.customer or _customer_of(orders),
		"status": _status(pick),
		"docstatus": pick.docstatus,
		"assignees": assignees,
		"mine": frappe.session.user in assignees,
		"lines": lines,
	}


def _customer_of(orders):
	return frappe.db.get_value("Sales Order", orders[0], "customer") if orders else None


def _status(pick):
	if pick.docstatus == 1:
		return "dispatched" if pick.status == "Completed" else "ready_to_dispatch"
	if any(row.cloud_wms_shortage_state == "Pending" for row in pick.locations):
		return "qa_required"
	if any(flt(row.picked_qty) or row.cloud_wms_location_confirmed for row in pick.locations):
		return "picking"
	return "claimed"


def _orders_of(pick):
	return sorted({row.sales_order for row in pick.locations if row.sales_order})


def _load(pick_list, ptype, for_update=False):
	if not pick_list or not frappe.db.exists("Pick List", pick_list):
		raise NotFound(f"Pick List {pick_list} does not exist.")
	pick = frappe.get_doc("Pick List", pick_list, for_update=for_update)
	pick.check_permission(ptype)
	return pick


def _load_draft(pick_list, assignee_only=True):
	pick = _load(pick_list, "write", for_update=True)
	if pick.docstatus != 0:
		raise Conflict(f"Pick List {pick.name} is already submitted.")
	assignees = _assignees(pick.name)
	if assignee_only:
		if frappe.session.user not in assignees and not _has_role(SUPERVISOR_ROLES):
			raise Forbidden(f"This task is assigned to {', '.join(assignees) or 'someone else'}.")
	elif not _has_role(SUPERVISOR_ROLES):
		raise Forbidden("Only a supervisor can do this.")
	return pick


def _row(pick, row):
	for line in pick.locations:
		if line.name == row:
			return line
	raise NotFound(f"Line {row} is not part of {pick.name}.")


def _ensure_no_pending_shortage(line):
	if line.cloud_wms_shortage_state == "Pending":
		raise Conflict("This line is waiting for supervisor approval of its shortage.", code="QA_REQUIRED")


def _clean_scan(value):
	value = (str(value).strip() if value is not None else "")
	if not value or len(value) > 140:
		raise InvalidRequest("A scanned value of up to 140 characters is required.")
	return value


def _positive_qty(qty):
	try:
		qty = flt(qty)
	except (TypeError, ValueError):
		qty = 0
	if qty <= 0:
		raise InvalidRequest("qty must be greater than zero.")
	return qty


def _matches_item(item_code, scanned):
	if scanned.casefold() == item_code.casefold():
		return True
	return frappe.db.get_value("Item Barcode", {"barcode": scanned}, "parent") == item_code


def _has_role(roles):
	return bool(set(roles) & set(frappe.get_roles()))


def _is_picker(user):
	if not frappe.db.get_value("User", user, "enabled"):
		return False
	return bool(frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": "WMS Picker"}))
