from django.db.models import Q
from django.utils.dateparse import parse_date


def filter_items(queryset, params):
    query = (params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(sku__icontains=query) | Q(name__icontains=query))

    category_id = params.get("category")
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    return queryset


def filter_categories(queryset, params):
    query = (params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(name__icontains=query)
    return queryset


def filter_movements(queryset, params):
    item_id = params.get("item")
    if item_id:
        queryset = queryset.filter(item_id=item_id)

    movement_type = params.get("movement_type")
    if movement_type:
        queryset = queryset.filter(movement_type=movement_type)

    location_id = params.get("location")
    if location_id:
        queryset = queryset.filter(
            Q(location_id=location_id)
            | Q(source_location_id=location_id)
            | Q(destination_location_id=location_id)
        )

    date_from = parse_date(params.get("date_from") or "")
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    date_to = parse_date(params.get("date_to") or "")
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    return queryset