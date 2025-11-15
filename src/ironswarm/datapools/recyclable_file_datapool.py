from itertools import chain

from ironswarm.datapools.file_datapool import FileDatapool


class RecyclableFileDatapool(FileDatapool):
    def __init__(self, filename: str):
        """
        Initialize a RecyclableFileDatapool with a file.

        See the FileDatapool docstring for details on initialization, arguments, and behavior.
        This class only adds wrap-around (recycling) behavior in checkout.
        """
        super().__init__(filename)
        self._recyclable = True

    def checkout(self, start: int = 0, stop: int | None = None):
        """
        Yield lines from the file between start (inclusive) and stop (exclusive), with wrap-around if stop < start.
        Uses metadata for fast seeking via _extract_chunk. Lines are 0-based.

        Args:
            start (int): Start line (inclusive).
            stop (int | None): Stop line (exclusive). If None, reads to end.

        Yields:
            str: Each line in the specified range, decoded and stripped.

        Behavior:
            - If stop < start, yields lines from start to end, then wraps to beginning and yields up to stop.
            - If stop == start, yields nothing.
            - Efficient for large files: does not load entire file into memory.

        Example:
            For lines 0..9, checkout(8, 2) yields lines 8, 9, 0, 1 (wrap-around).
        """
        if stop is not None and stop < start:
            first_chunk =  self._extract_chunk(start, len(self))
            second_chunk =  self._extract_chunk(0, stop)
            return chain(first_chunk, second_chunk)
        else:
            return self._extract_chunk(start, stop)
