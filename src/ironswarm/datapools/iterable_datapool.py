from collections.abc import Iterable
from functools import lru_cache

from ironswarm.datapools.base_datapool import DatapoolBase


class IterableDatapool(DatapoolBase):
    def __init__(self, iterable: Iterable):
        """
        Initialize an IterableDatapool with any Python iterable.

        Args:
            iterable (Iterable): The data source to use as the datapool.

        Raises:
            TypeError: If the provided data is not an Iterable.

        Notes:
            - The iterable is realized into a list once during initialization to ensure reusability.
            - This allows multiple checkout operations without exhausting the data source.
        """
        super().__init__()
        if not isinstance(iterable, Iterable):
            raise TypeError("Data must be an Iterable or None")
        # Realize the iterable into a list once to prevent exhaustion
        # This ensures the datapool is reusable and length is consistent
        self._items = list(iterable)

    @lru_cache
    def __len__(self):
        return len(self._items)

    def checkout(self, start: int = 0, stop: int | None = None):
        """
        Returns an iterator over items in the datapool from index 'start' (inclusive) to 'stop' (exclusive).

        Args:
            start (int): The starting index (inclusive).
            stop (int | None): The stopping index (exclusive). If None, iterate to the end.

        Returns:
            Iterator: An iterator over the selected items in the datapool.

        Example:
            checkout(2, 5) yields items at indices 2, 3, 4.
        """
        return iter(self._items[start:stop])
