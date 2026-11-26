"""Stock levels and stock postings for the WMS Admin role (admin screen 5).

Quantities change only through submitted ERPNext documents: Stock Entry (Material Receipt, Material
Transfer) and Stock Reconciliation (count). Postings run as the signed-in user, so ERPNext validation
and the WMS Admin permission rules apply. Each posting and each cancellation records an
`Inventory Corrected` event.
"""

import math

import frappe
from frappe.utils import cint, cstr

from cloud_wms.services import audit
from cloud_wms.services.admin import LIST_LIMIT, _check_modified, _default_company, _require
from cloud_wms.services.errors import Conflict, InvalidRequest

# UI purpose -> (doctype, ERPNext purpose)
PURPOSES = {
	"receipt": ("Stock Entry", "Material Receipt"),
	"transfer": ("Stock Entry", "Material Transfer"),
	"count": ("Stock Reconciliation", "Stock Reconciliation"),
}
POSTING_LIMIT = 50


def list_stock(search=None, warehouse=None):
	conditions = ["(bin.actual_qty != 0 or bin.reserved_stock != 0)"]
	values = {"limit": LIST_LIMIT}
	search = cstr(search).strip()
	if search:
		conditions.append(
			"(bin.item_code like %(search)s or item.item_name like %(search)s"
			" or bin.warehouse like %(search)s or wh.cloud_wms_location_barcode like %(search)s)"
		)
		values["search"] = f"%{search}%"
	if warehouse:
		_require("Warehouse", warehouse)
		lft, rgt = frappe.db.get_value("Warehouse", warehouse, ["lft", "rgt"])
		conditions.append("wh.lft >= %(lft)s and wh.rgt <= %(rgt)s")
		values.update(lft=lft, rgt=rgt)
	return frappe.db.sql(
		f"""
		select bin.item_code, item.item_name, bin.warehouse, wh.cloud_wms_location_barcode as barcode,
			bin.actual_qty, bin.reserved_stock, bin.projected_qty, bin.stock_uom, bin.valuation_rate
		from `tabBin` bin
		join `tabItem` item on item.name = bin.item_code
		join `tabWarehouse` wh on wh.name = bin.warehouse
		where {" and ".join(conditions)}
		order by wh.lft asc, bin.item_code asc
		limit %(limit)s
		""",
		values,
		as_dict=True,
	)


def list_postings(search=None):
	search = cstr(search).strip()
	entries = frappe.db.sql(
		"""
		select 'Stock Entry' as doctype, se.name, se.purpose, se.posting_date, se.posting_time, se.docstatus,
			se.owner, se.remarks, se.modified, se.creation,
			sed.item_code, sed.qty, sed.s_warehouse as from_warehouse, sed.t_warehouse as to_warehouse
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name and sed.idx = 1
		where se.purpose in ('Material Receipt', 'Material Transfer')
			and (%(search)s = '' or sed.item_code like %(like)s or se.name like %(like)s
				or sed.s_warehouse like %(like)s or sed.t_warehouse like %(like)s)
		order by se.creation desc
		limit %(limit)s
		""",
		{"search": search, "like": f"%{search}%", "limit": POSTING_LIMIT},
		as_dict=True,
	)
	counts = frappe.db.sql(
		"""
		select 'Stock Reconciliation' as doctype, sr.name, sr.purpose, sr.posting_date, sr.posting_time,
			sr.docstatus, sr.owner, null as remarks, sr.modified, sr.creation,
			sri.item_code, sri.qty, null as from_warehouse, sri.warehouse as to_warehouse
		from `tabStock Reconciliation` sr
		join `tabStock Reconciliation Item` sri on sri.parent = sr.name and sri.idx = 1
		where sr.purpose = 'Stock Reconciliation'
			and (%(search)s = '' or sri.item_code like %(like)s or sr.name like %(like)s
				or sri.warehouse like %(like)s)
		order by sr.creation desc
		limit %(limit)s
		""",
		{"search": search, "like": f"%{search}%", "limit": POSTING_LIMIT},
		as_dict=True,
	)
	rows = sorted(entries + counts, key=lambda row: row.creation, reverse=True)[:POSTING_LIMIT]
	for row in rows:
		row.pop("creation")
	return rows


def post_stock(purpose, item_code, qty, to_warehouse=None, from_warehouse=None, rate=None, reason=None):
	if purpose not in PURPOSES:
		raise InvalidRequest(f"Unknown stock posting {purpose!r}; use receipt, transfer or count.")
	_require("Item", item_code)
	if not cint(frappe.db.get_value("Item", item_code, "is_stock_item")):
		raise InvalidRequest(f"{item_code} is not a stock item.")
	qty = _quantity(qty, allow_zero=purpose == "count")
	rate = _rate(rate)
	reason = cstr(reason).strip()[:500] or None
	to_warehouse = _bin(to_warehouse, "to" if purpose != "count" else "counted")
	if purpose == "transfer":
		from_warehouse = _bin(from_warehouse, "from")
		if from_warehouse == to_warehouse:
			raise InvalidRequest("Choose two different locations for a transfer.")
	else:
		from_warehouse = None

	company = frappe.db.get_value("Warehouse", to_warehouse, "company") or _default_company()
	if from_warehouse and frappe.db.get_value("Warehouse", from_warehouse, "company") != company:
		raise InvalidRequest("Both locations of a transfer must belong to the same company.")

	doctype, erp_purpose = PURPOSES[purpose]
	if doctype == "Stock Entry":
		row = {"item_code": item_code, "qty": qty, "s_warehouse": from_warehouse, "t_warehouse": to_warehouse}
		if purpose == "receipt" and rate is not None:
			row["basic_rate"] = rate
		doc = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": _entry_type(erp_purpose),
				"purpose": erp_purpose,
				"company": company,
				"remarks": reason,
				"items": [row],
			}
		)
	else:
		row = {"item_code": item_code, "warehouse": to_warehouse, "qty": qty}
		if rate is not None:
			row["valuation_rate"] = rate
		doc = frappe.get_doc(
			{"doctype": "Stock Reconciliation", "purpose": erp_purpose, "company": company, "items": [row]}
		)
	doc.insert()
	doc.submit()

	audit.record_event(
		"Inventory Corrected",
		item_code=item_code,
		warehouse=to_warehouse,
		qty=qty,
		reason=reason,
		details={"action": purpose, "doctype": doctype, "name": doc.name, "from_warehouse": from_warehouse},
	)
	return _posting(doctype, doc.name)


def cancel_posting(doctype, name, modified=None, reason=None):
	if doctype not in ("Stock Entry", "Stock Reconciliation"):
		raise InvalidRequest("Only Stock Entries and Stock Reconciliations can be cancelled here.")
	_require(doctype, name)
	_check_modified(doctype, name, modified)
	doc = frappe.get_doc(doctype, name)
	if doc.purpose not in {purpose for _, purpose in PURPOSES.values()}:
		raise InvalidRequest(f"{name} is a {doc.purpose}; cancel it in ERPNext.")
	if doc.docstatus != 1:
		raise Conflict(f"{name} is not submitted.", next_action="Reload the postings.")
	doc.cancel()
	row = doc.items[0]
	audit.record_event(
		"Inventory Corrected",
		item_code=row.item_code,
		warehouse=row.get("t_warehouse") or row.get("warehouse"),
		qty=row.qty,
		reason=cstr(reason).strip()[:500] or None,
		details={"action": "cancel", "doctype": doctype, "name": name, "purpose": doc.purpose},
	)
	return _posting(doctype, name)


def _posting(doctype, name):
	return next(row for row in list_postings(name) if row.doctype == doctype and row.name == name)


def _entry_type(purpose):
	name = frappe.db.exists("Stock Entry Type", purpose) or frappe.db.get_value(
		"Stock Entry Type", {"purpose": purpose}
	)
	if not name:
		raise Conflict(
			f"No Stock Entry Type for {purpose} exists.",
			code="NOT_READY",
			next_action="Complete the ERPNext setup wizard or create the Stock Entry Type in Desk.",
		)
	return name


def _bin(warehouse, label):
	if not warehouse:
		raise InvalidRequest(f"Choose the {label} location.")
	_require("Warehouse", warehouse)
	is_group, disabled = frappe.db.get_value("Warehouse", warehouse, ["is_group", "disabled"])
	if cint(is_group):
		raise InvalidRequest(f"{warehouse} is a group; choose a bin.")
	if cint(disabled):
		raise InvalidRequest(f"{warehouse} is disabled.")
	return warehouse


def _quantity(value, allow_zero=False):
	qty = _number(value)
	if qty is None or qty < 0 or (qty == 0 and not allow_zero):
		raise InvalidRequest("Enter the counted quantity." if allow_zero else "Enter a quantity above zero.")
	return qty


def _rate(value):
	if value in (None, ""):
		return None
	rate = _number(value)
	if rate is None or rate < 0:
		raise InvalidRequest("The rate must be a number of zero or more.")
	return rate


def _number(value):
	try:
		number = float(value)
	except TypeError, ValueError:
		return None
	return number if math.isfinite(number) else None
