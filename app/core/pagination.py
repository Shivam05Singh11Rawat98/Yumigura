from collections.abc import Sequence
from typing import Any


def sort_and_paginate(
    items: Sequence[dict[str, Any]],
    *,
    sort_by: str,
    sort_order: str,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    reverse = sort_order == "desc"
    sorted_items = sorted(
        items,
        key=lambda item: (item.get(sort_by) is None, item.get(sort_by)),
        reverse=reverse,
    )
    return sorted_items[offset : offset + limit]
