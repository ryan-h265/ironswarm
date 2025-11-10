from abc import ABC, abstractmethod
from functools import lru_cache
from uuid import uuid4


class DatapoolBase(ABC):
    def __init__(self) -> None:
        """
        Base class for all datapools. Provides common attributes and initialization logic.

        Attributes:
            uuid (str): Unique identifier for the datapool instance.
            _iter: The underlying iterable for the datapool. Subclasses should set this appropriately.
            dp_len (int): Total length of the datapool (number of items). Should be set by subclasses.
            _recyclable (bool): Whether the datapool wraps around when chunking (default: False).

        Usage:
            - Subclass DatapoolBase and set _iter and dp_len in your implementation.
            - Use super().__init__() to ensure uuid and base attributes are initialized.
            - The datapool is assumed to be immutable after creation.
        """
        self.uuid = str(uuid4())
        self._iter = None
        self._recyclable = False
        self.index = 0

    def __repr__(self) -> str:
        return f"Datapool(uuid={self.uuid}, length={len(self)})"

    # @lru_cache prevents recalculation of expensive operations (e.g., counting file lines)
    #
    # ⚠️ IMPORTANT FOR SUBCLASS AUTHORS:
    # When overriding __len__, you MUST add @lru_cache decorator:
    #
    #     @lru_cache
    #     def __len__(self):
    #         return expensive_calculation()
    #
    # Without it, __len__ will be called repeatedly during scheduling, causing
    # severe performance degradation (O(n) file reads per schedule interval).
    @lru_cache
    @abstractmethod
    def __len__(self) -> int:
        pass

    # Future consideration: Enforce caching via wrapper pattern
    # This would eliminate the need for subclasses to remember @lru_cache
    #
    # Pattern: Base class caches, subclass implements _length()
    #
    # @lru_cache
    # def __len__(self):
    #     return self._length()  # Cached automatically
    #
    # @abstractmethod
    # def _length(self):
    #     pass  # Subclasses override this, caching handled by base
    #
    # Trade-off: More indirection, but enforces caching automatically

    @abstractmethod
    def checkout(self, start: int = 0, stop: int | None = None):
        """
        Returns an iterator over items in the datapool from index 'start' (inclusive) to 'stop' (exclusive).

        Note:
            This method must be implemented/extended in each concrete datapool extension.
            The base implementation does nothing and should be overridden to provide efficient access to the underlying data.

        Args:
            start (int): The starting index (inclusive).
            stop (int | None): The stopping index (exclusive). If None, iterate to the end.

        Returns:
            Iterator: An iterator over the selected items in the datapool.
        """
