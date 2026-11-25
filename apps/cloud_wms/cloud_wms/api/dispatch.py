import frappe

from cloud_wms.services import dispatch
from cloud_wms.services.endpoint import wms_endpoint


@frappe.whitelist(methods=["POST"])
@wms_endpoint("dispatch.confirm", roles=("WMS Dispatch",), idempotent=True)
def confirm(idempotency_key=None, pick_list=None, reference=None):
	return dispatch.confirm(pick_list, reference=reference)
