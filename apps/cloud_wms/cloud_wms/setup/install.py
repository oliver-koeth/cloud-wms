import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from cloud_wms.setup import permissions

CUSTOM_FIELDS = {
	"Sales Order": [
		{
			"fieldname": "cloud_wms_source",
			"label": "WMS Source",
			"fieldtype": "Data",
			"insert_after": "po_no",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
		},
		{
			"fieldname": "cloud_wms_external_order_id",
			"label": "WMS External Order ID",
			"fieldtype": "Data",
			"insert_after": "cloud_wms_source",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
		},
	],
	"Warehouse": [
		{
			"fieldname": "cloud_wms_location_barcode",
			"label": "WMS Location Barcode",
			"fieldtype": "Data",
			"insert_after": "warehouse_name",
			"unique": 1,
			"no_copy": 1,
		},
	],
}

STOCK_SETTINGS = {
	"enable_stock_reservation": 1,
	# Auto-reservation would make Pick List creation fail; reservation happens at pick completion.
	"auto_reserve_stock": 0,
}


def ensure_setup():
	"""Idempotent; runs after install and after every migrate."""
	permissions.ensure_roles()
	create_custom_fields(CUSTOM_FIELDS, update=True)
	permissions.ensure_permissions()
	ensure_stock_settings()


def ensure_stock_settings():
	for fieldname, value in STOCK_SETTINGS.items():
		if frappe.db.get_single_value("Stock Settings", fieldname) != value:
			frappe.db.set_single_value("Stock Settings", fieldname, value)
