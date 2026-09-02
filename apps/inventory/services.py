from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum

from apps.accounts.permissions import is_manager
from apps.locations.services import get_accessible_locations

from .models import StockMovement


def calculate_item_stock_by_location(item, location):
    """
    Rule 1: the ledger is the source of truth — this is a read-time
    aggregation over StockMovement, never a stored balance.

        Current Stock = Receipts + Incoming Transfers
                       − Issues − Outgoing Transfers
                       + Increase Adjustments − Decrease Adjustments
    """
    movements = StockMovement.objects.filter(item=item)

    def total(**filters):
        return movements.filter(**filters).aggregate(total=Sum("quantity"))["total"] or 0

    receipts = total(movement_type=StockMovement.MovementType.RECEIPT, location=location)
    issues = total(movement_type=StockMovement.MovementType.ISSUE, location=location)
    incoming_transfers = total(movement_type=StockMovement.MovementType.TRANSFER, destination_location=location)
    outgoing_transfers = total(movement_type=StockMovement.MovementType.TRANSFER, source_location=location)
    increase_adjustments = total(
        movement_type=StockMovement.MovementType.ADJUSTMENT, location=location,
        adjustment_direction=StockMovement.AdjustmentDirection.INCREASE,
    )
    decrease_adjustments = total(
        movement_type=StockMovement.MovementType.ADJUSTMENT, location=location,
        adjustment_direction=StockMovement.AdjustmentDirection.DECREASE,
    )

    return (
        receipts + incoming_transfers - issues - outgoing_transfers
        + increase_adjustments - decrease_adjustments
    )


def record_stock_movement(
    *, item, movement_type, quantity, recorded_by,
    location=None, source_location=None, destination_location=None,
    reason="", adjustment_direction=None,
):
    """
    The single validated entry point for creating a StockMovement.
    Both the template views and the DRF API call this — there is no
    second path that creates a movement, so there is no way for the two
    interfaces to enforce the rules differently.

    Enforces, in order: Rule 5 (archived items), quantity positivity,
    per-type required fields (Rules 3 & 4), Rule 3's balance check,
    Rule 7 (location access), then commits atomically.
    """
    if item.is_archived:
        raise ValidationError("Cannot record a movement for an archived item.")

    if quantity is None or quantity <= 0:
        raise ValidationError("Quantity must be a positive number.")

    if movement_type == StockMovement.MovementType.RECEIPT:
        if not location:
            raise ValidationError("Location is required for a Receipt.")
        source_location = destination_location = None
        adjustment_direction = None

    elif movement_type == StockMovement.MovementType.ISSUE:
        if not location:
            raise ValidationError("Location is required for an Issue.")
        source_location = destination_location = None
        adjustment_direction = None
        available = calculate_item_stock_by_location(item, location)
        if available < quantity:
            raise ValidationError(
                f"Insufficient stock at {location.code}: available {available}, requested {quantity}."
            )

    elif movement_type == StockMovement.MovementType.TRANSFER:
        if not source_location or not destination_location:
            raise ValidationError("Both source and destination locations are required for a Transfer.")
        if source_location == destination_location:
            raise ValidationError("Source and destination locations must be different.")
        location = None
        adjustment_direction = None
        available = calculate_item_stock_by_location(item, source_location)
        if available < quantity:
            raise ValidationError(
                f"Insufficient stock at {source_location.code}: available {available}, "
                f"requested {quantity}. Transfer rejected — negative stock is never allowed."
            )

    elif movement_type == StockMovement.MovementType.ADJUSTMENT:
        if not is_manager(recorded_by):
            raise PermissionDenied("Only Inventory Managers can record adjustments.")
        if not reason or not reason.strip():
            raise ValidationError("Reason is required for an Adjustment.")
        if not location:
            raise ValidationError("Location is required for an Adjustment.")
        if adjustment_direction not in (
            StockMovement.AdjustmentDirection.INCREASE,
            StockMovement.AdjustmentDirection.DECREASE,
        ):
            raise ValidationError("Adjustment direction (Increase/Decrease) is required.")
        source_location = destination_location = None
        if adjustment_direction == StockMovement.AdjustmentDirection.DECREASE:
            available = calculate_item_stock_by_location(item, location)
            if available < quantity:
                raise ValidationError(
                    f"Insufficient stock at {location.code} to decrease by {quantity}; "
                    f"available {available}."
                )

    else:
        raise ValidationError("Unknown movement type.")

    # Rule 7: Staff may only record movements touching locations they're assigned to.
    if not is_manager(recorded_by):
        touched = [loc for loc in (location, source_location, destination_location) if loc]
        accessible_ids = set(get_accessible_locations(recorded_by).values_list("pk", flat=True))
        if any(loc.pk not in accessible_ids for loc in touched):
            raise PermissionDenied("You do not have access to one or more of the selected locations.")

    with transaction.atomic():
        movement = StockMovement.objects.create(
            item=item,
            movement_type=movement_type,
            quantity=quantity,
            location=location,
            source_location=source_location,
            destination_location=destination_location,
            adjustment_direction=adjustment_direction,
            reason=reason,
            recorded_by=recorded_by,
        )

    return movement