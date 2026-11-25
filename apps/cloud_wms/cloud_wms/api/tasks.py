import frappe

from cloud_wms.services import tasks
from cloud_wms.services.endpoint import wms_endpoint

PICKERS = ("WMS Picker", "WMS Supervisor")
READERS = ("WMS Picker", "WMS Supervisor", "WMS Dispatch")


@frappe.whitelist(methods=["GET"])
@wms_endpoint("tasks.list", roles=READERS)
def list_tasks():
	return tasks.list_tasks()


@frappe.whitelist(methods=["GET"])
@wms_endpoint("tasks.get", roles=READERS)
def get(pick_list=None, sales_order=None):
	return tasks.get_task(pick_list=pick_list, sales_order=sales_order)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.claim", roles=PICKERS, idempotent=True)
def claim(idempotency_key=None, sales_order=None, assignee=None):
	return tasks.claim(sales_order, assignee=assignee)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.release", roles=PICKERS, idempotent=True)
def release(idempotency_key=None, pick_list=None):
	return tasks.release(pick_list)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.confirm_location", roles=PICKERS, idempotent=True)
def confirm_location(idempotency_key=None, pick_list=None, row=None, barcode=None):
	return tasks.confirm_location(pick_list, row, barcode)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.confirm_pick", roles=PICKERS, idempotent=True)
def confirm_pick(idempotency_key=None, pick_list=None, row=None, item_barcode=None, qty=1):
	return tasks.confirm_pick(pick_list, row, item_barcode, qty)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.record_shortage", roles=PICKERS, idempotent=True)
def record_shortage(idempotency_key=None, pick_list=None, row=None, reason=None):
	return tasks.record_shortage(pick_list, row, reason)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.approve_shortage", roles=("WMS Supervisor",), idempotent=True)
def approve_shortage(idempotency_key=None, pick_list=None, row=None):
	return tasks.approve_shortage(pick_list, row)


@frappe.whitelist(methods=["POST"])
@wms_endpoint("tasks.complete", roles=PICKERS, idempotent=True)
def complete(idempotency_key=None, pick_list=None):
	return tasks.complete(pick_list)
