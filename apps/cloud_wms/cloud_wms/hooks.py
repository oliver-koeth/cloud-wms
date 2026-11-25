app_name = "cloud_wms"
app_title = "Cloud WMS"
app_publisher = "Cloud WMS"
app_description = "Warehouse workflow API over ERPNext Sales Orders, Pick Lists and Delivery Notes"
app_email = "wms@cloud-wms.local"
app_license = "mit"

required_apps = ["erpnext"]

after_install = "cloud_wms.setup.install.ensure_setup"
after_migrate = "cloud_wms.setup.install.ensure_setup"
