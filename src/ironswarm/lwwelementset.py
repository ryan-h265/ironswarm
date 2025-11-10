from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


class LWWElementSet:
    """
    Conflict-free replicated data type
    LWW-Element-Set (Last-Write-Wins-Element-Set)
    """

    def __init__(self) -> None:
        """
        One side affect of using `defaultdict` is when we lookup an element in
        e.g. `self.remove_set[element]`
        When you access a non-existent key in a defaultdict, it automatically
        inserts the key with a default value
        """
        # element -> dict including timestamp and optional metadata
        self.add_set: defaultdict[Any, dict[str, Any]] = defaultdict(dict)
        self.remove_set: defaultdict[Any, dict[str, Any]] = defaultdict(dict)

    def add(
        self, element: Any, timestamp: float | None = None, **added_values: Any
    ) -> None:
        """Add element to set with timestamp and metadata."""
        timestamp = timestamp or time.time()
        old_ts = self.add_set[element].get("timestamp", 0.0)

        if timestamp >= old_ts:
            self.add_set[element] = {"timestamp": timestamp, **added_values}

    def remove(
        self, element: Any, timestamp: float | None = None, **removed_values: Any
    ) -> None:
        """Remove element from set with timestamp.

        Note: potentially confusing having `removed_values`
        do we omit this parameter and removing an element removes
        its complete corresponding dictionary, no partial edits...
        """
        timestamp = timestamp or time.time()
        old_ts = self.remove_set[element].get("timestamp", 0.0)

        if timestamp >= old_ts:
            self.remove_set[element] = {"timestamp": timestamp, **removed_values}

    def lookup(self, element: Any) -> dict[str, Any] | bool:
        """Check if element is in set and return its metadata.

        Returns:
            Dictionary with element metadata if present, False otherwise.
        """
        add_ts = self.add_set[element].get("timestamp", 0.0)
        remove_ts = self.remove_set[element].get("timestamp", 0.0)

        if add_ts > remove_ts:
            return self.add_set[element]
        else:
            return False

    def keys(self) -> set[Any]:
        """Get set of all current elements.

        Returns:
            Set of element keys currently in the set.
        """
        return {e for e in self.add_set if self.lookup(e)}

    def values(self) -> list[tuple[Any, dict[str, Any]]]:
        """Get list of (element, metadata) tuples for all current elements.

        Returns:
            List of (element, metadata) tuples for iteration.
            Returns tuples (not dict) to support unpacking in loops:
            `for key, metadata in lww.values():`
        """
        return [(e, m) for e, m in self.add_set.items() if self.lookup(e)]

    def merge(self, other: LWWElementSet) -> None:
        """Merge another LWW-Element-Set into this one.

        Args:
            other: Another LWWElementSet to merge from.
        """
        for e, meta in other.add_set.items():
            if not meta.get("timestamp"):
                continue
            self.add(
                e,
                **{k: v for k, v in meta.items() if k != "timestamp"},
                timestamp=meta["timestamp"],
            )
        for e, meta in other.remove_set.items():
            if not meta.get("timestamp"):
                continue
            self.remove(
                e,
                **{k: v for k, v in meta.items() if k != "timestamp"},
                timestamp=meta["timestamp"],
            )

    def to_dict(self) -> dict[str, dict[Any, dict[str, Any]]]:
        """Convert to dictionary representation for serialization.

        Returns:
            Dictionary with 'add_set' and 'remove_set' keys.
        """
        return {
            "add_set": dict(self.add_set),
            "remove_set": dict(self.remove_set),
        }

    @classmethod
    def from_dict(cls, data: dict[str, dict[Any, dict[str, Any]]]) -> LWWElementSet:
        """Create LWWElementSet from dictionary representation.

        Args:
            data: Dictionary with 'add_set' and 'remove_set' keys.

        Returns:
            New LWWElementSet instance.
        """
        lww = cls()
        lww.add_set = defaultdict(dict, data["add_set"])
        lww.remove_set = defaultdict(dict, data["remove_set"])

        return lww
