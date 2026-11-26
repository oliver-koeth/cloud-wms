"""Audit log, reference lists and settings for the WMS Admin role (admin screens 8, 9 and 10)."""

import frappe
from frappe.utils import cint, cstr, getdate

from cloud_wms.services import admin
from cloud_wms.services.admin import LIST_LIMIT, _require
from cloud_wms.services.errors import Conflict, InvalidRequest

EVENT_FIELDS = [
	"name",
	"creation",
	"event_type",
	"actor",
	"correlation_id",
	"idempotency_key",
	"sales_order",
	"pick_list",
	"pick_list_item",
	"delivery_note",
	"item_code",
	"warehouse",
	"scanned_value",
	"qty",
	"reason",
	"details",
]
EVENT_FILTERS = ("event_type", "actor", "sales_order", "pick_list", "delivery_note", "correlation_id")

# Tree doctypes the admin can extend: doctype -> (name field, parent field)
TREES = {
	"Customer Group": ("customer_group_name", "parent_customer_group"),
	"Territory": ("territory_name", "parent_territory"),
	"Item Group": ("item_group_name", "parent_item_group"),
}
FLAT = {
	"UOM": ["name", "enabled", "must_be_whole_number"],
	"Price List": ["name", "currency", "selling", "buying", "enabled"],
}
STOCK_SETTINGS = (
	"enable_stock_reservation",
	"auto_reserve_stock",
	"allow_partial_reservation",
	"allow_negative_stock",
	"valuation_method",
	"over_picking_allowance",
	"over_delivery_receipt_allowance",
	"pick_serial_and_batch_based_on",
	"item_group",
	"stock_uom",
)
SELLING_SETTINGS = ("selling_price_list", "customer_group", "territory", "so_required", "dn_required")


# Audit log


def list_events(from_date=None, to_date=None, **filters):
	conditions = {
		key: cstr(filters.get(key)).strip() for key in EVENT_FILTERS if cstr(filters.get(key)).strip()
	}
	if from_date or to_date:
		start = _date(from_date, "from") or getdate("2000-01-01")
		end = _date(to_date, "to") or getdate("2999-12-31")
		if start > end:
			raise InvalidRequest("The start date is after the end date.")
		conditions["creation"] = ["between", [f"{start} 00:00:00", f"{end} 23:59:59.999999"]]
	return {
		"events": frappe.get_all(
			"WMS Task Event",
			filters=conditions,
			fields=EVENT_FIELDS,
			order_by="creation desc",
			limit=LIST_LIMIT,
		),
		"event_types": event_types(),
		"limit": LIST_LIMIT,
	}


def event_types():
	options = frappe.get_meta("WMS Task Event").get_field("event_type").options
	return [option for option in (options or "").split("\n") if option]


def _date(value, label):
	if not value:
		return None
	try:
		return getdate(value)
	except frappe.ValidationError, TypeError, ValueError:
		raise InvalidRequest(f"The {label} date is not a valid date.") from None


# Reference lists


def list_reference(doctype):
	if doctype in TREES:
		parent_field = TREES[doctype][1]
		rows = frappe.get_all(
			doctype, fields=["name", f"{parent_field} as parent", "is_group", "lft"], order_by="lft asc"
		)
		depth = {}
		for row in rows:
			depth[row.name] = depth.get(row.parent, -1) + 1 if row.parent else 0
			row["depth"] = depth[row.name]
			row.pop("lft")
		return {"doctype": doctype, "tree": True, "rows": rows}
	if doctype in FLAT:
		rows = frappe.get_all(doctype, fields=FLAT[doctype], order_by="name asc", limit=1000)
		return {"doctype": doctype, "tree": False, "rows": rows}
	raise InvalidRequest(f"{doctype} is not a reference list; use {', '.join([*TREES, *FLAT])}.")


def create_reference(doctype, name, parent=None, is_group=0):
	if doctype not in TREES:
		raise InvalidRequest(f"New {doctype} records are created in ERPNext Desk.")
	name = cstr(name).strip()
	if not name:
		raise InvalidRequest("Enter a name.")
	if len(name) > 140:
		raise InvalidRequest("The name may be at most 140 characters.")
	if frappe.db.exists(doctype, name):
		raise Conflict(f"{doctype} {name} already exists.", code="DUPLICATE")
	name_field, parent_field = TREES[doctype]
	parent = cstr(parent).strip() or frappe.db.get_value(
		doctype, {parent_field: ["is", "not set"]}, "name", order_by="lft asc"
	)
	_require(doctype, parent)
	if not cint(frappe.db.get_value(doctype, parent, "is_group")):
		raise InvalidRequest(f"{parent} is not a group; choose a group as the parent.")
	doc = frappe.get_doc(
		{"doctype": doctype, name_field: name, parent_field: parent, "is_group": 1 if cint(is_group) else 0}
	)
	doc.insert()
	admin._record(doctype, doc.name, "created")
	return {"name": doc.name, "parent": parent, "is_group": doc.is_group}


# Settings


def settings():
	stock = frappe.get_cached_doc("Stock Settings")
	selling = frappe.get_cached_doc("Selling Settings")
	return {
		"stock": {field: stock.get(field) for field in STOCK_SETTINGS},
		"selling": {field: selling.get(field) for field in SELLING_SETTINGS},
		"enforced": _enforced(),
		"companies": frappe.get_all(
			"Company", fields=["name", "abbr", "default_currency", "country"], order_by="name asc"
		),
		"default_company": admin._default_company(),
		"versions": {app: _version(app) for app in ("frappe", "erpnext", "cloud_wms")},
	}


def _enforced():
	from cloud_wms.setup.install import STOCK_SETTINGS as ENFORCED

	return dict(ENFORCED)


def _version(app):
	try:
		return frappe.get_attr(f"{app}.__version__")
	except AttributeError, ImportError:
		return None
