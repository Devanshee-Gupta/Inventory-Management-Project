# Schema

## Profile

* id (AutoField)
* user (OneToOneField)
* role (CharField)
* created_at (DateTimeField)
* updated_at (DateTimeField)

## Category

* id (AutoField)
* name (CharField, unique)
* description (TextField)
* created_by (ForeignKey)
* created_at (DateTimeField)
* updated_at (DateTimeField)

## Item

* id (AutoField)
* sku (CharField, unique)
* name (CharField)
* description (TextField)
* unit_of_measure (CharField)
* reorder_level (PositiveIntegerField)
* category (ForeignKey)
* is_archived (BooleanField)
* created_by (ForeignKey)
* created_at (DateTimeField)
* updated_at (DateTimeField)

## Location

* id (AutoField)
* name (CharField)
* code (CharField, unique)
* description (TextField)
* is_active (BooleanField)
* created_at (DateTimeField)
* updated_at (DateTimeField)

## StaffLocationAssignment

* id (AutoField)
* staff (ForeignKey)
* location (ForeignKey)
* assigned_at (DateTimeField)

## StockMovement

* id (AutoField)
* item (ForeignKey)
* movement_type (CharField)
* quantity (PositiveIntegerField)
* location (ForeignKey)
* source_location (ForeignKey)
* destination_location (ForeignKey)
* adjustment_direction (CharField)
* reason (TextField)
* recorded_by (ForeignKey)
* created_at (DateTimeField)

## ItemHistory

* id (AutoField)
* item (ForeignKey)
* event_type (CharField)
* field_name (CharField)
* old_value (TextField)
* new_value (TextField)
* note (TextField)
* performed_by (ForeignKey)
* created_at (DateTimeField)

## LowStockAlert

* id (AutoField)
* item (ForeignKey)
* dismissed (BooleanField)
* dismissed_by (ForeignKey)
* dismissed_at (DateTimeField)
* created_at (DateTimeField)

## Relationships

One-to-Many:

* Category → Items
* Item → Stock Movements
* Item → Item History
* Location → Stock Movements
* User → Created Items
* User → Recorded Movements

Many-to-Many:

* User ↔ Location through StaffLocationAssignment

## Constraints

Database constraints:

* Unique SKU
* Unique category name
* Unique location code
* Foreign key integrity
* Positive quantity validation

Application-level constraints:

* Negative stock prevention
* Transfer validation
* Adjustment reason requirement
* Role-based permissions
* Location assignment checks
* Archive restrictions
* Immutable ledger entries

I kept these rules in application code because they depend on business logic rather than simple database constraints.

## What did you deliberately denormalise?

I deliberately did not store stock balances directly. Inventory quantities are derived from stock movement records whenever required.

## What would break first if this had 100x the data?

The dashboard and stock calculations would be affected first because they depend on repeated aggregation of ledger entries. Additional indexing, caching, and reporting tables would be required for large-scale usage.

---
