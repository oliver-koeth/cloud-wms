import frappe
from frappe.utils import add_days, getdate, nowdate

TEST_COMPANY = "WMS Test Co"
TEST_ABBR = "WTC"
TEST_CUSTOMER = "WMS Test Customer"
TEST_PRICE_LIST = "WMS Test Selling"
TEST_ITEM = "WMS-TEST-ITEM"
TEST_ITEM_2 = "WMS-TEST-ITEM-2"
TEST_WAREHOUSE_NAME = "WMS Test Shelf"


def ensure_master_data():
	"""Create the minimum ERPNext master data on a bare test site; returns names used by tests."""
	frappe.set_user("Administrator")
	_ensure_fiscal_year()
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Company", TEST_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": TEST_COMPANY,
				"abbr": TEST_ABBR,
				"default_currency": "INR",
				"country": "Germany",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("Price List", TEST_PRICE_LIST):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": TEST_PRICE_LIST,
				"currency": "INR",
				"selling": 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.set_single_value("Selling Settings", "selling_price_list", TEST_PRICE_LIST)
	if not frappe.db.exists("Customer", TEST_CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": TEST_CUSTOMER,
				"customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}),
			}
		).insert(ignore_permissions=True)
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	if not frappe.db.exists("Item Group", "All Item Groups"):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "All Item Groups", "is_group": 1}
		).insert(ignore_permissions=True)
	for code in (TEST_ITEM, TEST_ITEM_2):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"standard_rate": 10,
				}
			).insert(ignore_permissions=True)
	warehouse = f"{TEST_WAREHOUSE_NAME} - {TEST_ABBR}"
	if not frappe.db.exists("Warehouse", warehouse):
		frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": TEST_WAREHOUSE_NAME, "company": TEST_COMPANY}
		).insert(ignore_permissions=True)
	frappe.db.commit()
	return {
		"company": TEST_COMPANY,
		"customer": TEST_CUSTOMER,
		"item": TEST_ITEM,
		"item_2": TEST_ITEM_2,
		"warehouse": warehouse,
	}


def _ensure_fiscal_year():
	today = getdate(nowdate())
	covered = frappe.db.sql(
		"select name from `tabFiscal Year` where year_start_date <= %s and year_end_date >= %s",
		(add_days(today, 1), today),
	)
	if covered:
		return
	frappe.get_doc(
		{
			"doctype": "Fiscal Year",
			"year": f"WMS-TEST-{today.year}",
			"year_start_date": f"{today.year}-01-01",
			"year_end_date": f"{today.year}-12-31",
		}
	).insert(ignore_permissions=True)


def ensure_user(email, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"user_type": "System User",
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)
	return email
