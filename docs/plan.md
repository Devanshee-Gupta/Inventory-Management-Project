# Plan

## How did you break the work into sessions?

Session 1:

* Project setup
* Database design
* Authentication setup

Session 2:

* Category and item management

Session 3:

* Location management and staff assignments

Session 4:

* Stock movement implementation

Session 5:

* Ledger calculations and inventory validation

Session 6:

* Dashboard, alerts and item history

Session 7:

* CSV import/export

Session 8:

* Testing, bug fixes and deployment

## What order did you build in, and why that order?

Authentication was implemented first because all permissions depend on user roles.

Items, categories and locations were created next because stock movements depend on those entities.

The stock ledger was built before dashboards because all reporting relies on movement data.

Dashboards, alerts and history tracking were added after the core inventory workflow was functioning correctly.

## What did you estimate versus what it actually took?

Authentication and roles:
Estimated: 1 hour
Actual: 2 hours

Stock movement logic:
Estimated: 2 hours
Actual: 3 hours

Dashboard:
Estimated: 1.5 hours
Actual: 3 hours

Deployment:
Estimated: 30 minutes
Actual: 1.5 hours

## What did you cut when you ran short?

* Supplier management
* Email alerts
* Advanced analytics

---