# PRD Source

The implementation follows `C:/Users/PC/Downloads/Product Requirements Document - PharmaLink MVP.pdf`.

Implemented MVP scope:

- Django REST backend with modular apps for accounts, pharmacies, medicines, inventory, imports, sales, prescriptions, and audit logs.
- Next.js TypeScript frontend with public search, login, pharmacy workspace, and admin workspace.
- PostgreSQL-ready configuration through Docker Compose.
- UUID primary keys, role-based permissions, pharmacy-scoped protected querysets, soft active/public flags, private prescription downloads, audit logs, import preview/confirm, and FEFO stock deduction for sales.
- Focused backend tests for permission boundaries, public search privacy, stock deduction, and prescription access.

Non-goals preserved:

- No diagnosis, treatment advice, automatic substitution recommendations, payment processing, insurance claims, native mobile app, microservices, Kafka, Kubernetes, blockchain, or public prescription access.

