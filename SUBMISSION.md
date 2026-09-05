# Submission

## Links

* **GitHub repository:** https://github.com/Devanshee-Gupta/Inventory-Management-Project
* **Live application:** https://devansheegupta.pythonanywhere.com/

## Notes for the reviewer

The application is deployed on PythonAnywhere using the free hosting tier.

The system has been seeded with sample inventory data to demonstrate stock movements, transfers, dashboard statistics, item history tracking, low-stock alerts, and role-based access control.

All inventory balances are derived from stock ledger entries rather than being stored directly, following the assignment requirements.

## Demo credentials

| Role              | Email                     | Password      |
| ----------------- | ------------------------- | ------------- |
| Inventory Manager | Manager1 | DemoPass123! |
| Warehouse Staff   | staff_wh01   | DemoPass123! |
| Warehouse Staff   | staff_store01   | DemoPass123! |

## Stack

| Layer    | What you used                  | Why                                                 |
| -------- | ------------------------------ | --------------------------------------------------- |
| Frontend | Django Templates + Bootstrap 5 | Fast development and tight integration with Django  |
| Backend  | Django                         | Built-in authentication, ORM, and rapid development |
| Database | SQLite                         | Lightweight and sufficient for assignment scope     |
| Hosting  | PythonAnywhere                 | Free deployment with simple Django support          |

## Goal checklist

| #  | Goal                       | Status | Notes                                                     |
| -- | -------------------------- | ------ | --------------------------------------------------------- |
| 1  | Accounts and roles         | Done   | Manager and warehouse staff roles enforced on server side |
| 2  | Items                      | Done   | Category management, archive and restore supported        |
| 3  | Stock movements            | Done   | Receipt, issue, transfer and adjustment implemented       |
| 4  | Stock ledger               | Done   | Append-only ledger, balances derived from movements       |
| 5  | Location assignment        | Done   | Staff can be assigned to multiple locations               |
| 6  | Finding items              | Done   | Search, filtering, sorting and pagination implemented     |
| 7  | Bulk import and export     | Done   | CSV import and export functionality implemented           |
| 8  | Dashboard                  | Done   | Summary metrics and stock insights available              |
| 9  | History you cannot rewrite | Done   | Immutable item history and notes                          |
| 10 | Low-stock alerts           | Done   | Alert dismissal and reappearance logic implemented        |

## How much time did you actually spend?

Approximately 13–14 hours spread across multiple development sessions.

## What would you do next, with another 12 hours?

* Add supplier management
* Add email notifications for low-stock alerts
* Optimize dashboard queries for larger datasets

## What are you least happy with in this codebase, and why?

The dashboard currently calculates several statistics dynamically from ledger data. While this approach keeps the data accurate, it would become a performance bottleneck with a significantly larger dataset. In a production environment I would introduce caching or reporting tables to reduce repeated aggregation work.

---

