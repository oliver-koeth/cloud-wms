import frappe

from cloud_wms.services import orders
from cloud_wms.services.endpoint import wms_endpoint


@frappe.whitelist(methods=["POST"])
@wms_endpoint("orders.ingest", roles=("WMS Intake",), idempotent=True)
def ingest(
	idempotency_key=None,
	source=None,
	customer=None,
	company=None,
	delivery_date=None,
	lines=None,
	external_order_id=None,
	set_warehouse=None,
):
	return orders.ingest_order(
		source=source,
		customer=customer,
		company=company,
		delivery_date=delivery_date,
		lines=lines,
		external_order_id=external_order_id,
		set_warehouse=set_warehouse,
	)
