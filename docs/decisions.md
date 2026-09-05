# Decisions

## Decision 1

* **Chose:** Append-only stock ledger
* **Rejected:** Editable inventory balances
* **Why:** Maintaining an immutable ledger provides traceability and prevents inventory changes without recorded movements.

## Decision 2

* **Chose:** Django Templates
* **Rejected:** React frontend
* **Why:** Using Django templates reduced complexity and allowed more focus on implementing business requirements within the available time.

## Decision 3

* **Chose:** SQLite
* **Rejected:** PostgreSQL
* **Why:** SQLite was sufficient for assignment scale and simplified deployment.

## Decision 4

* **Chose:** Separate Profile model for roles
* **Rejected:** Storing role information directly on the User model
* **Why:** Keeping role-specific information in a separate model provides cleaner separation of concerns.

## Decision 5

* **Chose:** Staff-to-location assignment table
* **Rejected:** Single location per staff member
* **Why:** The assignment required staff to be assigned to multiple locations.

**Later reversed:** Initially I considered storing inventory balances directly for faster queries. During implementation I changed the design and calculated balances entirely from ledger entries because the assignment explicitly required inventory quantities to be derived from stock movements.

---