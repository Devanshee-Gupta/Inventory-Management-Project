# Architecture

## What are the moving pieces, and how do they talk to each other?

The system consists of four main parts:

1. Django web application
2. SQLite database
3. Authentication and authorization layer
4. Inventory ledger and reporting logic

Users interact with Django views through their browser. Django processes requests, applies permission checks, executes business rules, and stores or retrieves data through the ORM. Dashboard metrics, stock calculations, alerts, and history records are generated from the stored ledger data.

## Where does each piece run?

* Browser: User interface rendered through Django templates
* Application Server: Django application running on PythonAnywhere
* Database: SQLite database hosted with the application

## What is the request path for one representative user action?

Example: Warehouse staff records a stock issue.

1. User submits the stock issue form.
2. Django verifies authentication.
3. Server checks whether the staff member is assigned to the selected location.
4. Business rules validate available stock.
5. A StockMovement ledger entry is created.
6. Inventory balances are recalculated from ledger data.
7. Related dashboards and alerts automatically reflect the updated stock position.
8. Success response is returned to the user.

## What did you decide not to build, and why?

I deliberately did not implement optional stretch features such as barcode scanning, supplier management, cycle counting, email notifications, and batch tracking.

The goal was to complete all required functionality first and ensure the core inventory workflow was stable and compliant with the assignment requirements.

---