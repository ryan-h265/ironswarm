from collections.abc import Iterable, Iterator
from itertools import chain
from typing import Any

from ironswarm.datapools.iterable_datapool import IterableDatapool


class RecyclableDatapool(IterableDatapool):
    def __init__(self, iterable: Iterable):
        """
        Initialize a RecyclableDatapool with any Python iterable.

        See the IterableDatapool docstring for details on initialization, arguments, and behavior.
        This class only adds wrap-around (recycling) behavior in checkout.
        """
        super().__init__(iterable)
        self._recyclable = True

    def checkout(self, start: int = 0, stop: int | None = None) -> Iterator[Any]:
        """
        Returns an iterator over items in the datapool from index 'start' (inclusive) to 'stop' (exclusive),
        recycling to the beginning if stop < start.

        Args:
            start (int): The starting index (inclusive).
            stop (int | None): The stopping index (exclusive). If None, iterate to the end.

        Returns:
            Iterator[Any]: An iterator over the selected items in the datapool, with wrap-around if needed.

        Raises:
            ValueError: If start is negative, start exceeds datapool length, or stop is negative.

        Behavior:
            - If stop < start, yields items from start to end, then from 0 to stop (wrap-around).
            - Otherwise, yields items from start to stop as usual.

        Example:
            checkout(8, 2) yields items at indices 8, 9, 0, 1 (wrap-around).
        """
        # Validate start index
        if start < 0:
            raise ValueError(f"start must be non-negative, got {start}")

        if start > len(self):
            raise ValueError(f"start index {start} exceeds datapool length {len(self)}")

        # Validate stop index if provided
        if stop is not None and stop < 0:
            raise ValueError(f"stop must be non-negative, got {stop}")

        if stop is not None and stop < start:
            # Wrap around: from start to end, then from beginning to stop
            first_chunk = iter(self._items[start:])
            second_chunk = iter(self._items[:stop])
            return chain(first_chunk, second_chunk)
        else:
            return iter(self._items[start:stop])

