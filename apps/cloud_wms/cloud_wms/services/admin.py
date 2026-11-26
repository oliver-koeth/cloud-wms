"""Master data and Sales Order administration for the WMS Admin role.

Writes run as the signed-in user, so ERPNext validation and the WMS Admin permission rules apply.
Reads are role-gated by the endpoint and return only what the admin screens show.
"""

import json

import frappe
from frappe.utils import cint, cstr, flt

from cloud_wms.services import audit, orders, tasks
from cloud_wms.services.errors import Conflict, InvalidRequest, NotFound

LIST_LIMIT = 200
DELETABLE = ("Customer", "Item", "Warehouse")
ADDRESS_FIELDS = ("address_line1", "address_line2", "city", "pincode", "country")
ORDER_FIELDS = [
	"name",
	"customer",
	"customer_name",
	"company",
	"transaction_date",
	"delivery_date",
	"set_warehouse",
	"status",
	"docstatus",
	"grand_total",
	"currency",
	"per_picked",
	"per_delivered",
	"amended_from",
	"cloud_wms_source",
	"cloud_wms_external_order_id",
	"modified",
]


def options():
	return {
		"companies": frappe.get_all("Company", pluck="name", order_by="name asc"),
		"default_company": _default_company(),
		"customer_groups": frappe.get_all(
			"Customer Group", filters={"is_group": 0}, pluck="name", order_by="name asc"
		),
		"territories": frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", order_by="name asc"),
		"item_groups": frappe.get_all("Item Group", pluck="name", order_by="name asc"),
		"uoms": frappe.get_all("UOM", filters={"enabled": 1}, pluck="name", order_by="name asc"),
		"countries": frappe.get_all("Country", pluck="name", order_by="name asc"),
		"selling_price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list"),
	}


def _default_company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")


# Customers


def list_customers(search=None, include_disabled=0):
	return frappe.get_all(
		"Customer",
		filters=None if cint(include_disabled) else {"disabled": 0},
		or_filters=_search(search, "name", "customer_name"),
		fields=["name", "customer_name", "customer_type", "customer_group", "territory", "disabled", "email_id"],
		order_by="customer_name asc",
		limit=LIST_LIMIT,
	)


def get_customer(name):
	_require("Customer", name)
	customer = frappe.db.get_value(
		"Customer",
		name,
		[
			"name",
			"customer_name",
			"customer_type",
			"customer_group",
			"territory",
			"disabled",
			"email_id",
			"mobile_no",
			"customer_primary_address",
			"customer_primary_contact",
			"modified",
		],
		as_dict=True,
	)
	address = {}
	if customer.customer_primary_address:
		address = (
			frappe.db.get_value("Address", customer.customer_primary_address, ADDRESS_FIELDS, as_dict=True)
			or {}
		)
	customer["address"] = {field: address.get(field) for field in ADDRESS_FIELDS}
	customer["open_orders"] = frappe.db.count(
		"Sales Order", {"customer": name, "docstatus": 1, "status": ["not in", ("Completed", "Closed")]}
	)
	return customer


def save_customer(
	name=None,
	customer_name=None,
	customer_type=None,
	customer_group=None,
	territory=None,
	disabled=0,
	email_id=None,
	mobile_no=None,
	address=None,
	modified=None,
):
	customer_name = cstr(customer_name).strip()
	if not customer_name:
		raise InvalidRequest("customer_name is required.")
	address = _clean_address(address)
	email_id = cstr(email_id).strip() or None
	mobile_no = cstr(mobile_no).strip() or None

	if name:
		_require("Customer", name)
		_check_modified("Customer", name, modified)
		doc = frappe.get_doc("Customer", name)
	else:
		doc = frappe.new_doc("Customer")
	doc.customer_name = customer_name
	doc.customer_type = customer_type or doc.customer_type or "Company"
	doc.customer_group = customer_group or doc.customer_group or _first_leaf("Customer Group")
	doc.territory = territory or doc.territory or _first_leaf("Territory")
	doc.disabled = cint(disabled)

	if doc.is_new():
		# ERPNext creates the primary Contact and Address from these on insert.
		doc.email_id, doc.mobile_no = email_id, mobile_no
		if address:
			doc.update(address)
		doc.insert()
		action = "created"
	else:
		doc.save()
		_upsert_contact(doc, email_id, mobile_no)
		_upsert_address(doc, address)
		action = "updated"
	_record("Customer", doc.name, action)
	return get_customer(doc.name)


def _clean_address(address):
	if isinstance(address, str):
		try:
			address = json.loads(address) if address.strip() else None
		except ValueError:
			raise InvalidRequest("address must be a JSON object.") from None
	if not address:
		return None
	if not isinstance(address, dict):
		raise InvalidRequest("address must be an object.")
	cleaned = {field: cstr(address.get(field)).strip() or None for field in ADDRESS_FIELDS}
	if not any(cleaned.values()):
		return None
	missing = [field for field in ("address_line1", "city", "country") if not cleaned[field]]
	if missing:
		raise InvalidRequest(f"An address needs {', '.join(missing)}.")
	return cleaned


def _upsert_contact(customer, email_id, mobile_no):
	if customer.customer_primary_contact:
		contact = frappe.get_doc("Contact", customer.customer_primary_contact)
		_set_primary_row(contact, "email_ids", "email_id", "is_primary", email_id)
		_set_primary_row(contact, "phone_nos", "phone", "is_primary_mobile_no", mobile_no)
		contact.save()
	elif email_id or mobile_no:
		from erpnext.selling.doctype.customer.customer import make_contact

		customer.email_id, customer.mobile_no = email_id, mobile_no
		contact = make_contact(customer)
		customer.db_set("customer_primary_contact", contact.name)
	else:
		return
	customer.db_set({"email_id": email_id, "mobile_no": mobile_no})


def _set_primary_row(contact, table, field, flag, value):
	rows = contact.get(table)
	primary = next((row for row in rows if row.get(flag)), None)
	if value and primary:
		primary.set(field, value)
	elif value:
		contact.append(table, {field: value, flag: 1})
	elif primary:
		contact.set(table, [row for row in rows if row is not primary])


def _upsert_address(customer, address):
	if not address:
		return
	from frappe.contacts.doctype.address.address import get_address_display

	if customer.customer_primary_address:
		doc = frappe.get_doc("Address", customer.customer_primary_address)
		doc.update(address)
		doc.save()
	else:
		from erpnext.selling.doctype.customer.customer import make_address

		customer.update(address)
		doc = make_address(customer)
		customer.db_set("customer_primary_address", doc.name)
	customer.db_set("primary_address", get_address_display(doc.name))


# Products


def list_items(search=None, include_disabled=0):
	items = frappe.get_all(
		"Item",
		filters=None if cint(include_disabled) else {"disabled": 0},
		or_filters=_search(search, "name", "item_name"),
		fields=["name", "item_name", "item_group", "stock_uom", "is_stock_item", "disabled"],
		order_by="item_name asc",
		limit=LIST_LIMIT,
	)
	names = [item.name for item in items]
	barcodes, on_hand = {}, {}
	if names:
		for row in frappe.get_all(
			"Item Barcode",
			filters={"parent": ["in", names], "parenttype": "Item"},
			fields=["parent", "barcode"],
			order_by="idx asc",
		):
			barcodes.setdefault(row.parent, []).append(row.barcode)
		on_hand = dict(
			frappe.db.sql(
				"select item_code, sum(actual_qty) from `tabBin` where item_code in %(items)s group by item_code",
				{"items": tuple(names)},
			)
		)
	for item in items:
		item["barcodes"] = barcodes.get(item.name, [])
		item["on_hand"] = flt(on_hand.get(item.name))
	return items


def get_item(name):
	_require("Item", name)
	item = frappe.db.get_value(
		"Item",
		name,
		["name", "item_name", "item_group", "stock_uom", "is_stock_item", "disabled", "description", "modified"],
		as_dict=True,
	)
	item["barcodes"] = frappe.get_all(
		"Item Barcode", filters={"parent": name, "parenttype": "Item"}, pluck="barcode", order_by="idx asc"
	)
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	item["selling_price_list"] = price_list
	item["selling_rate"] = (
		frappe.db.get_value("Item Price", {"item_code": name, "price_list": price_list}, "price_list_rate")
		if price_list
		else None
	)
	item["stock"] = frappe.get_all(
		"Bin",
		filters={"item_code": name, "actual_qty": ["!=", 0]},
		fields=["warehouse", "actual_qty", "reserved_stock"],
		order_by="warehouse asc",
	)
	return item


def save_item(
	name=None,
	item_code=None,
	item_name=None,
	item_group=None,
	stock_uom=None,
	is_stock_item=None,
	description=None,
	disabled=0,
	barcodes=None,
	selling_rate=None,
	modified=None,
):
	barcodes = _clean_barcodes(barcodes)
	rate = _clean_rate(selling_rate)
	if name:
		_require("Item", name)
		_check_modified("Item", name, modified)
		doc = frappe.get_doc("Item", name)
	else:
		item_code = cstr(item_code).strip()
		if not item_code:
			raise InvalidRequest("item_code is required.")
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.stock_uom = stock_uom or "Nos"
		doc.is_stock_item = 1 if is_stock_item is None else cint(is_stock_item)
	doc.item_name = cstr(item_name).strip() or doc.item_name or doc.item_code
	doc.item_group = item_group or doc.item_group or "All Item Groups"
	if not doc.is_new():
		# ERPNext refuses these changes once the item has stock ledger entries.
		if stock_uom:
			doc.stock_uom = stock_uom
		if is_stock_item is not None:
			doc.is_stock_item = cint(is_stock_item)
	if description is not None:
		doc.description = cstr(description).strip() or doc.item_name
	doc.disabled = cint(disabled)
	if barcodes is not None:
		taken = frappe.get_all(
			"Item Barcode",
			filters={"barcode": ["in", barcodes or [""]], "parent": ["!=", doc.name or ""]},
			fields=["barcode", "parent"],
			limit=1,
		)
		if taken:
			raise Conflict(f"Barcode {taken[0].barcode} is already used by item {taken[0].parent}.", code="DUPLICATE")
		kept = {row.barcode: row for row in doc.barcodes}
		doc.set(
			"barcodes",
			[
				{"barcode": code, "barcode_type": kept[code].barcode_type, "uom": kept[code].uom}
				if code in kept
				else {"barcode": code}
				for code in barcodes
			],
		)
	if rate is not None:
		# On insert ERPNext creates the selling Item Price from standard_rate.
		doc.standard_rate = rate

	action = "created" if doc.is_new() else "updated"
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	if rate is not None:
		_set_selling_rate(doc.name, rate)
	_record("Item", doc.name, action)
	return get_item(doc.name)


def _clean_barcodes(barcodes):
	if barcodes is None:
		return None
	if isinstance(barcodes, str):
		try:
			barcodes = json.loads(barcodes)
		except ValueError:
			raise InvalidRequest("barcodes must be a JSON array.") from None
	if not isinstance(barcodes, list):
		raise InvalidRequest("barcodes must be a list.")
	cleaned = []
	for code in barcodes:
		code = cstr(code).strip()
		if code and code not in cleaned:
			cleaned.append(code)
	return cleaned


def _clean_rate(value):
	if value in (None, ""):
		return None
	try:
		rate = float(value)
	except (TypeError, ValueError):
		raise InvalidRequest("selling_rate must be a number.") from None
	if rate < 0:
		raise InvalidRequest("selling_rate cannot be negative.")
	return rate


def _set_selling_rate(item_code, rate):
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if not price_list:
		return
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list}, "name")
	if name:
		price = frappe.get_doc("Item Price", name)
		if flt(price.price_list_rate) != rate:
			price.price_list_rate = rate
			price.save()
		return
	frappe.get_doc(
		{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": rate}
	).insert()


# Locations


def list_locations(include_disabled=1):
	rows = frappe.get_all(
		"Warehouse",
		filters=None if cint(include_disabled) else {"disabled": 0},
		fields=[
			"name",
			"warehouse_name",
			"parent_warehouse",
			"is_group",
			"disabled",
			"company",
			"cloud_wms_location_barcode",
			"lft",
			"rgt",
			"modified",
		],
		order_by="lft asc",
	)
	on_hand = dict(frappe.db.sql("select warehouse, sum(actual_qty) from `tabBin` group by warehouse"))
	depth = {}
	for row in rows:
		depth[row.name] = depth.get(row.parent_warehouse, -1) + 1 if row.parent_warehouse else 0
	for row in rows:
		row["barcode"] = row.pop("cloud_wms_location_barcode")
		row["depth"] = depth[row.name]
		row["on_hand"] = sum(
			flt(on_hand.get(other.name)) for other in rows if row.lft <= other.lft and other.rgt <= row.rgt
		)
	for row in rows:
		row.pop("lft")
		row.pop("rgt")
	return rows


def save_location(
	name=None,
	warehouse_name=None,
	parent_warehouse=None,
	is_group=0,
	barcode=None,
	disabled=0,
	company=None,
	modified=None,
):
	is_group = cint(is_group)
	barcode = cstr(barcode).strip() or None
	parent_warehouse = parent_warehouse or None
	if is_group and barcode:
		raise InvalidRequest("Only a bin can have a location barcode; a group cannot.")
	if parent_warehouse:
		_require("Warehouse", parent_warehouse)
		if not frappe.db.get_value("Warehouse", parent_warehouse, "is_group"):
			raise InvalidRequest(f"{parent_warehouse} is a bin. Choose a group as the parent.")

	if name:
		_require("Warehouse", name)
		_check_modified("Warehouse", name, modified)
		doc = frappe.get_doc("Warehouse", name)
	else:
		warehouse_name = cstr(warehouse_name).strip()
		if not warehouse_name:
			raise InvalidRequest("warehouse_name is required.")
		doc = frappe.new_doc("Warehouse")
		doc.warehouse_name = warehouse_name
		doc.company = (
			company
			or (parent_warehouse and frappe.db.get_value("Warehouse", parent_warehouse, "company"))
			or _default_company()
		)
	if barcode:
		taken = frappe.db.get_value(
			"Warehouse", {"cloud_wms_location_barcode": barcode, "name": ["!=", doc.name or ""]}, "name"
		)
		if taken:
			raise Conflict(f"Barcode {barcode} is already used by location {taken}.", code="DUPLICATE")
	doc.parent_warehouse = parent_warehouse
	doc.is_group = is_group
	doc.cloud_wms_location_barcode = barcode
	doc.disabled = cint(disabled)

	action = "created" if doc.is_new() else "updated"
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	_record("Warehouse", doc.name, action)
	return next(row for row in list_locations() if row.name == doc.name)


# Records


def delete_record(doctype, name):
	if doctype not in DELETABLE:
		raise InvalidRequest(f"doctype must be one of {', '.join(DELETABLE)}.")
	_require(doctype, name)
	try:
		frappe.delete_doc(doctype, name)
	except frappe.LinkExistsError:
		raise Conflict(
			f"{doctype} {name} is used by other records and cannot be deleted.",
			code="IN_USE",
			next_action="Disable it instead.",
		) from None
	_record(doctype, name, "deleted")
	return {"doctype": doctype, "name": name, "deleted": True}


# Sales Orders


def list_orders(search=None, status=None):
	return frappe.get_all(
		"Sales Order",
		filters={"status": status} if status else None,
		or_filters=_search(search, "name", "customer", "customer_name", "cloud_wms_external_order_id"),
		fields=[field for field in ORDER_FIELDS if field not in ("set_warehouse", "modified")],
		order_by="creation desc",
		limit=LIST_LIMIT,
	)


def get_order(name):
	_require("Sales Order", name)
	order = frappe.db.get_value("Sales Order", name, ORDER_FIELDS, as_dict=True)
	order["items"] = frappe.get_all(
		"Sales Order Item",
		filters={"parent": name, "parenttype": "Sales Order"},
		fields=["name", "item_code", "item_name", "qty", "uom", "rate", "amount", "picked_qty", "delivered_qty"],
		order_by="idx asc",
	)
	order["pick_lists"] = tasks.pick_lists_for_order(name)
	notes = _delivery_notes_of(name)
	order["delivery_notes"] = (
		frappe.get_all(
			"Delivery Note",
			filters={"docstatus": ["<", 2], "name": ["in", notes]},
			fields=["name", "docstatus", "status"],
		)
		if notes
		else []
	)
	order["amended_to"] = frappe.db.get_value("Sales Order", {"amended_from": name}, "name")
	order["cancel_blocker"] = _cancel_blocker(order)
	return order


def cancel_order(sales_order, modified=None):
	order = _load_submitted(sales_order, modified)
	order.cancel()
	audit.record_event("Order Cancelled", sales_order=order.name)
	return get_order(order.name)


def amend_order(sales_order, lines, delivery_date=None, customer=None, modified=None):
	"""Cancel a submitted order (if not already cancelled) and submit its amendment in one transaction."""
	_require("Sales Order", sales_order)
	original = frappe.get_doc("Sales Order", sales_order)
	if original.docstatus == 0:
		raise Conflict(f"{sales_order} is a draft; it can be edited in ERPNext directly.")
	amended_to = frappe.db.get_value("Sales Order", {"amended_from": sales_order}, "name")
	if amended_to:
		raise Conflict(
			f"{sales_order} was already amended as {amended_to}.", next_action=f"Edit {amended_to} instead."
		)
	delivery_date = delivery_date or original.delivery_date
	items = orders.clean_lines(lines, delivery_date)
	if original.docstatus == 1:
		_load_submitted(sales_order, modified).cancel()

	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"amended_from": original.name,
			"customer": customer or original.customer,
			"company": original.company,
			"delivery_date": delivery_date,
			"set_warehouse": original.set_warehouse,
			"po_no": original.po_no,
			"items": items,
			"cloud_wms_source": original.cloud_wms_source,
			"cloud_wms_external_order_id": original.cloud_wms_external_order_id,
		}
	)
	doc.insert()
	doc.submit()
	audit.record_event(
		"Order Amended",
		sales_order=doc.name,
		details={"amended_from": original.name, "lines": len(items)},
	)
	return get_order(doc.name)


def _load_submitted(sales_order, modified):
	_require("Sales Order", sales_order)
	_check_modified("Sales Order", sales_order, modified)
	order = frappe.get_doc("Sales Order", sales_order)
	blocker = _cancel_blocker(order)
	if blocker:
		raise Conflict(blocker["message"], code="ORDER_IN_USE", next_action=blocker["next_action"])
	return order


def _cancel_blocker(order):
	if order.docstatus != 1:
		return {"message": f"{order.name} is not submitted.", "next_action": None}
	if order.status == "Closed":
		return {"message": f"{order.name} is closed.", "next_action": "Reopen it in ERPNext first."}
	for pick in tasks.pick_lists_for_order(order.name):
		if pick.docstatus == 0:
			return {
				"message": f"Pick task {pick.name} is open for {order.name}.",
				"next_action": "Release it from the Pick screen first.",
			}
		return {
			"message": f"Pick List {pick.name} is submitted for {order.name}.",
			"next_action": "A supervisor must cancel the Pick List and any Delivery Note in ERPNext first.",
		}
	notes = [
		note
		for note in _delivery_notes_of(order.name)
		if frappe.db.get_value("Delivery Note", note, "docstatus") == 1
	]
	if notes:
		return {
			"message": f"Delivery Note {notes[0]} is submitted for {order.name}.",
			"next_action": "Cancel the Delivery Note in ERPNext first.",
		}
	return None


def _delivery_notes_of(sales_order):
	return frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": sales_order, "parenttype": "Delivery Note"},
		pluck="parent",
		distinct=True,
	)


# Helpers


def _require(doctype, name):
	if not name or not frappe.db.exists(doctype, name):
		raise NotFound(f"{doctype} {name or '(no name)'} does not exist.")


def _check_modified(doctype, name, modified):
	if modified and cstr(frappe.db.get_value(doctype, name, "modified")) != cstr(modified):
		raise Conflict(
			f"{doctype} {name} was changed by someone else.",
			code="STALE",
			next_action="Reload it and apply your change again.",
		)


def _search(search, *fields):
	search = cstr(search).strip()
	if not search:
		return None
	return [[field, "like", f"%{search}%"] for field in fields]


def _first_leaf(doctype):
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


def _record(doctype, name, action):
	audit.record_event("Master Data Changed", details={"doctype": doctype, "name": name, "action": action})
