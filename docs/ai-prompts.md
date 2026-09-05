
# AI Prompts

## Initial project architecture

### Prompt

Design a Django-based inventory management system that uses an append-only stock ledger instead of storing inventory balances directly.

### What I got

Suggested models for items, locations, users, and stock movements.

### What I corrected

Adjusted the schema to match the exact assignment requirements and added role-specific permissions.

## Authentication and authorization

### Prompt

Implement role-based access control for inventory managers and warehouse staff in Django.

### What I got

Role-based permissions and authentication workflow.

### What I corrected

Added location assignment checks so staff could only perform actions in assigned locations.

## Stock ledger implementation

### Prompt

How should inventory balances be calculated using stock movement records?

### What I got

A ledger-based calculation approach.

### What I corrected

Added transfer-specific logic and validation to prevent invalid stock movements.

## Dashboard implementation

### Prompt

Generate dashboard metrics for inventory activity and stock analysis.

### What I got

Aggregate query suggestions.

### What I corrected

Modified queries to match assignment requirements and available data structures.

## Example of incorrect AI output

### Prompt

How should stock transfers be recorded?

### What I got

The AI suggested maintaining separate editable inventory balances alongside movement records.

### What I corrected

Removed direct balance storage and implemented calculations entirely from ledger entries to comply with assignment requirements and preserve auditability.
