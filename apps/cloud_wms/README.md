# Cloud WMS (Frappe app)

Custom Frappe app that adds the warehouse workflow on top of unmodified ERPNext:
Sales Order intake, Pick List claim/pick/complete, and Delivery Note dispatch.

Phase 1 (this version) provides the foundation only:

- WMS roles and the permission matrix (`cloud_wms.setup.permissions`)
- Custom fields and Stock Settings (`cloud_wms.setup.install`)
- `WMS Request` (idempotency) and `WMS Task Event` (immutable audit) DocTypes
- Error envelope, idempotency service and the `wms_endpoint` decorator
- `cloud_wms.api.session.context` smoke endpoint
- Local demo users and demo warehouse locations (`cloud_wms.setup.demo`)

See `ARCHITECTURE.md` in the repository root.
