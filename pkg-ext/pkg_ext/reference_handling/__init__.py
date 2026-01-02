# Reference add/remove handling domain

from .added import handle_added_refs, handle_added_refs_flat
from .removed import handle_removed_refs, handle_removed_refs_flat

__all__ = [
    "handle_added_refs",
    "handle_added_refs_flat",
    "handle_removed_refs",
    "handle_removed_refs_flat",
]
