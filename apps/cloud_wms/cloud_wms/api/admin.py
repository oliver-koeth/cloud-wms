import frappe

from cloud_wms.services import admin, admin_documents, admin_reference, admin_stock
from cloud_wms.services.endpoint import wms_endpoint

ADMIN = ("WMS Admin",)
# Exception handling on Pick Lists and Delivery Notes is shared with supervisors.
DOCUMENTS = ("WMS Admin", "WMS Supervisor")


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.options", roles=ADMIN)
def options():
	return admin.options()


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_customers", roles=ADMIN)
def list_customers(search=None, include_disabled=0):
	return admin.list_customers(search, include_disabled)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.get_customer", roles=ADMIN)
def get_customer(name=None):
	return admin.get_customer(name)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.save_customer", roles=ADMIN, idempotent=True)
def save_customer(
	idempotency_key=None,
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
	return admin.save_customer(
		name=name,
		customer_name=customer_name,
		customer_type=customer_type,
		customer_group=customer_group,
		territory=territory,
		disabled=disabled,
		email_id=email_id,
		mobile_no=mobile_no,
		address=address,
		modified=modified,
	)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_items", roles=ADMIN)
def list_items(search=None, include_disabled=0):
	return admin.list_items(search, include_disabled)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.get_item", roles=ADMIN)
def get_item(name=None):
	return admin.get_item(name)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.save_item", roles=ADMIN, idempotent=True)
def save_item(
	idempotency_key=None,
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
	return admin.save_item(
		name=name,
		item_code=item_code,
		item_name=item_name,
		item_group=item_group,
		stock_uom=stock_uom,
		is_stock_item=is_stock_item,
		description=description,
		disabled=disabled,
		barcodes=barcodes,
		selling_rate=selling_rate,
		modified=modified,
	)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_locations", roles=ADMIN)
def list_locations(include_disabled=1):
	return admin.list_locations(include_disabled)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.save_location", roles=ADMIN, idempotent=True)
def save_location(
	idempotency_key=None,
	name=None,
	warehouse_name=None,
	parent_warehouse=None,
	is_group=0,
	barcode=None,
	disabled=0,
	company=None,
	modified=None,
):
	return admin.save_location(
		name=name,
		warehouse_name=warehouse_name,
		parent_warehouse=parent_warehouse,
		is_group=is_group,
		barcode=barcode,
		disabled=disabled,
		company=company,
		modified=modified,
	)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.delete_record", roles=ADMIN, idempotent=True)
def delete_record(idempotency_key=None, doctype=None, name=None):
	return admin.delete_record(doctype, name)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_orders", roles=ADMIN)
def list_orders(search=None, status=None):
	return admin.list_orders(search, status)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.get_order", roles=ADMIN)
def get_order(name=None):
	return admin.get_order(name)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.cancel_order", roles=ADMIN, idempotent=True)
def cancel_order(idempotency_key=None, sales_order=None, modified=None):
	return admin.cancel_order(sales_order, modified=modified)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.amend_order", roles=ADMIN, idempotent=True)
def amend_order(
	idempotency_key=None, sales_order=None, lines=None, delivery_date=None, customer=None, modified=None
):
	return admin.amend_order(
		sales_order, lines, delivery_date=delivery_date, customer=customer, modified=modified
	)


# Stock (screen 5)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_stock", roles=ADMIN)
def list_stock(search=None, warehouse=None):
	return admin_stock.list_stock(search, warehouse)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_postings", roles=ADMIN)
def list_postings(search=None):
	return admin_stock.list_postings(search)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.post_stock", roles=ADMIN, idempotent=True)
def post_stock(
	idempotency_key=None,
	purpose=None,
	item_code=None,
	qty=None,
	to_warehouse=None,
	from_warehouse=None,
	rate=None,
	reason=None,
):
	return admin_stock.post_stock(
		purpose,
		item_code,
		qty,
		to_warehouse=to_warehouse,
		from_warehouse=from_warehouse,
		rate=rate,
		reason=reason,
	)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.cancel_posting", roles=ADMIN, idempotent=True)
def cancel_posting(idempotency_key=None, doctype=None, name=None, modified=None, reason=None):
	return admin_stock.cancel_posting(doctype, name, modified=modified, reason=reason)


# Pick Lists and Delivery Notes (screen 7)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_pick_lists", roles=DOCUMENTS)
def list_pick_lists(search=None, status=None):
	return admin_documents.list_pick_lists(search, status)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.get_pick_list", roles=DOCUMENTS)
def get_pick_list(name=None):
	return admin_documents.get_pick_list(name)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.cancel_pick_list", roles=DOCUMENTS, idempotent=True)
def cancel_pick_list(idempotency_key=None, pick_list=None, modified=None, reason=None):
	return admin_documents.cancel_pick_list(pick_list, modified=modified, reason=reason)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_delivery_notes", roles=DOCUMENTS)
def list_delivery_notes(search=None, status=None):
	return admin_documents.list_delivery_notes(search, status)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.get_delivery_note", roles=DOCUMENTS)
def get_delivery_note(name=None):
	return admin_documents.get_delivery_note(name)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.cancel_delivery_note", roles=DOCUMENTS, idempotent=True)
def cancel_delivery_note(idempotency_key=None, delivery_note=None, modified=None, reason=None):
	return admin_documents.cancel_delivery_note(delivery_note, modified=modified, reason=reason)


# Audit log, reference lists, settings (screens 8-10)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_events", roles=ADMIN)
def list_events(
	event_type=None,
	actor=None,
	sales_order=None,
	pick_list=None,
	delivery_note=None,
	correlation_id=None,
	from_date=None,
	to_date=None,
):
	return admin_reference.list_events(
		from_date=from_date,
		to_date=to_date,
		event_type=event_type,
		actor=actor,
		sales_order=sales_order,
		pick_list=pick_list,
		delivery_note=delivery_note,
		correlation_id=correlation_id,
	)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.list_reference", roles=ADMIN)
def list_reference(doctype=None):
	return admin_reference.list_reference(doctype)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("admin.create_reference", roles=ADMIN, idempotent=True)
def create_reference(idempotency_key=None, doctype=None, name=None, parent=None, is_group=0):
	return admin_reference.create_reference(doctype, name, parent=parent, is_group=is_group)


@frappe.whitelist(methods=["GET"])
@wms_endpoint("admin.settings", roles=ADMIN)
def settings():
	return admin_reference.settings()
