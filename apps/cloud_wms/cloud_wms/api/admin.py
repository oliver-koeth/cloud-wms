import frappe

from cloud_wms.services import admin
from cloud_wms.services.endpoint import wms_endpoint

ADMIN = ("WMS Admin",)


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
