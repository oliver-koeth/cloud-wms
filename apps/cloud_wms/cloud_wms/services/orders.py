import json
import re

import frappe
from frappe.utils import flt

from cloud_wms.services import audit, tasks
from cloud_wms.services.errors import InvalidRequest

SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,39}$")
MAX_EXTERNAL_ID_LENGTH = 140
MAX_LINES = 200


def ingest_order(source, customer, company, delivery_date, lines, external_order_id=None, set_warehouse=None):
	"""Create and submit a Sales Order as the current user; return its WMS-facing summary."""
	source = _clean_source(source)
	external_order_id = _clean_external_id(external_order_id)
	items = _clean_lines(lines, delivery_date)
	if not (customer and company and delivery_date):
		raise InvalidRequest("customer, company and delivery_date are required.")

	if external_order_id:
		existing = _find_existing(source, external_order_id)
		if existing:
			return _summary(existing, duplicate=True)

	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"delivery_date": delivery_date,
			"set_warehouse": set_warehouse or None,
			"items": items,
			"cloud_wms_source": source,
			"cloud_wms_external_order_id": external_order_id,
		}
	)
	doc.insert()
	doc.submit()

	audit.record_event(
		"Order Received",
		sales_order=doc.name,
		details={"source": source, "external_order_id": external_order_id, "lines": len(items)},
	)
	return _summary(doc.name, duplicate=False)


def _clean_source(source):
	source = (source or "").strip().lower()
	if not SOURCE_PATTERN.match(source):
		raise InvalidRequest("source must be 1-40 characters of a-z, 0-9, '-' or '_'.")
	return source


def _clean_external_id(value):
	value = (str(value).strip() if value is not None else "") or None
	if value and len(value) > MAX_EXTERNAL_ID_LENGTH:
		raise InvalidRequest(f"external_order_id must be at most {MAX_EXTERNAL_ID_LENGTH} characters.")
	return value


def _clean_lines(lines, delivery_date):
	if isinstance(lines, str):
		try:
			lines = json.loads(lines)
		except ValueError:
			raise InvalidRequest("lines must be a JSON array.") from None
	if not isinstance(lines, list) or not lines:
		raise InvalidRequest("At least one order line is required.")
	if len(lines) > MAX_LINES:
		raise InvalidRequest(f"An order may have at most {MAX_LINES} lines.")

	items = []
	for index, line in enumerate(lines, start=1):
		if not isinstance(line, dict) or not line.get("item_code"):
			raise InvalidRequest(f"Line {index}: item_code is required.")
		try:
			qty = flt(line.get("qty"))
		except (TypeError, ValueError):
			qty = 0
		if qty <= 0:
			raise InvalidRequest(f"Line {index}: qty must be greater than zero.")
		row = {"item_code": line["item_code"], "qty": qty, "delivery_date": delivery_date}
		if line.get("rate") not in (None, ""):
			row["rate"] = flt(line["rate"])
		if line.get("uom"):
			row["uom"] = line["uom"]
		items.append(row)
	return items


def _find_existing(source, external_order_id):
	return frappe.db.get_value(
		"Sales Order",
		{"cloud_wms_source": source, "cloud_wms_external_order_id": external_order_id, "docstatus": ["<", 2]},
		"name",
		order_by="creation asc",
	)


def _summary(name, duplicate):
	order = frappe.db.get_value(
		"Sales Order", name, ["name", "docstatus", "status", "per_delivered", "customer"], as_dict=True
	)
	pick_lists = tasks.pick_lists_for_order(name)
	return {
		"sales_order": order.name,
		"customer": order.customer,
		"docstatus": order.docstatus,
		"status": order.status,
		"pick_list": pick_lists[0].name if pick_lists else None,
		"duplicate": duplicate,
	}
