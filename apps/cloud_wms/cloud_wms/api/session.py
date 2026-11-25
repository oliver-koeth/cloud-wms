import frappe

import cloud_wms
from cloud_wms.services.endpoint import WMS_ROLES, wms_endpoint


@frappe.whitelist(methods=["GET"])
@wms_endpoint("session.context", roles=WMS_ROLES)
def context():
	user = frappe.session.user
	user_roles = set(frappe.get_roles(user))
	warehouses = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Warehouse"},
		pluck="for_value",
	)
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"roles": [role for role in (*WMS_ROLES, "System Manager") if role in user_roles],
		"warehouses": sorted(warehouses),
		"app_version": cloud_wms.__version__,
	}
