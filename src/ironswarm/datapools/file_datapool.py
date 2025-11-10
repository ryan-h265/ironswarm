import os
from collections.abc import Callable, Generator
from functools import lru_cache

from ironswarm.datapools.base_datapool import DatapoolBase


class FileDatapool(DatapoolBase):
    def __init__(self, filename: str):
        """
        Initialize a FileDatapool extension, which provides efficient line-based access to a file.

        This extension:
            - Accepts a filename and checks for its existence.
            - Creates or loads a metadata file for fast seeking to line boundaries.
            - Calculates the total number of lines in the file and sets dp_len.
            - Allows chunked and indexed access to file lines via the checkout method.

        Args:
            filename (str): Path to the file to be used as a datapool.

        Raises:
            FileNotFoundError: If the specified file does not exist.
        """
        super().__init__()
        self.filename = filename
        # TODO I feel like we should give the option to rebuild the metadata file without having to delete them manually everytime
        # Set the dummy value to False for now.
        self.force_metadata_creation = False

        # check for the datapool file and raise error if needed
        if not os.path.exists(filename):
            raise FileNotFoundError(f"{filename} doesn't exist.")

        # check for metadata, create if not exists
        self.meta_filename = os.path.join(
        os.path.dirname(filename), f".{os.path.basename(filename)}.meta"
        )

        if not os.path.exists(self.meta_filename) or self.force_metadata_creation:
            self._process_data_file()

    @lru_cache
    def __len__(self):
        # Go to the last line of the meta file and extract its content
        # Seek the position on the file and iterate until the eof counting the lines
        with open(self.meta_filename) as mf:
            for line in mf:
                pass
            line_number, seek_point = line.strip().split(',')
        with open(self.filename, "rb") as f:
            f.seek(int(seek_point))
            current_line_number = int(line_number)
            for _ in f:  # type: bytes
                current_line_number += 1
        return current_line_number

    def checkout(self, start: int = 0, stop: int | None = None):
        """
        Yields lines from the file between the specified start and stop line numbers (inclusive of start, exclusive of stop).
        Uses the metadata file for efficient seeking, minimizing reads for large files.

        Args:
            start (int): The starting line number (0-based, inclusive).
            stop (int | None): The ending line number (0-based, exclusive). If None, reads until the end of the file.

        Yields:
            str: Each line in the file within the specified range, decoded as UTF-8 and stripped of whitespace.

        Behavior:
            - If 'start' is beyond the end of the file, yields nothing.
            - If 'stop' is less than or equal to 'start', yields nothing.
            - Lines are counted starting from 0.
            - Uses the metadata file for fast seeking; assumes the metadata file exists (created in __init__).
            - Efficient for large files: does not load the entire file into memory.

        Example:
            For a file with lines 0..9, checkout(2, 5) yields lines 2, 3, 4.
        """
        return self._extract_chunk(start, stop)

    def _extract_chunk(self, start: int, stop: int | None = None):
        """
        Efficiently yield lines from the file between start (inclusive) and stop (exclusive).
        Uses metadata to seek close to the start line for fast access in large files.

        Args:
            start (int): Line number to start reading from (inclusive, 0-based).
            stop (int): Line number to stop reading at (exclusive). If None, reads to end.

        Yields:
            str: Each line in the specified range, decoded as UTF-8 and stripped.

        Behavior:
            - If start is beyond the end of the file, yields nothing.
            - If stop is less than or equal to start, yields nothing.
            - Lines are counted from 0.
            - Efficient for large files: does not load the entire file into memory.

        Example:
            For lines 0..9, _extract_chunk(2, 5) yields lines 2, 3, 4.
        """
        # Find the closest seek point and line number using the meta file
        closest_point = self._seek_closest_point(start) if start else (0, 0)
        closest_line_number, closest_seek_point = closest_point

        # Open the file and seek to the closest point and read the lines
        with open(self.filename, "rb") as f:
            f.seek(closest_seek_point)
            current_line_number = closest_line_number
            for line in f:  # type: bytes
                current_line_number += 1
                if current_line_number > start:
                    yield line.decode("utf-8").strip()
                if stop and current_line_number >= stop:
                    break

    def _seek_closest_point(self, start: int):
        """
        Finds the closest line number and byte seek point in the metadata file that is less than or equal to 'start'.
        This enables efficient seeking in large files by jumping to a known position near the desired line, then scanning forward.

        Args:
            start (int): The target line number to seek to.

        Returns:
            tuple: (closest_line_number, closest_seek_point) where closest_line_number <= start.
        """
        closest_line_number = 0
        closest_seek_point = 0
        with open(self.meta_filename) as mf:
            for meta_line in mf:
                line_number, seek_point = map(int, meta_line.strip().split(","))
                if line_number <= start:
                    closest_line_number = line_number
                    closest_seek_point = seek_point
                else:
                    break
        return closest_line_number, closest_seek_point

    def _process_data_file(self, buffer_size: int = 1024 * 1024):
        """
        Processes the file to generate a metadata file for fast line-based seeking.

        Reads the file in chunks, counts lines, and writes metadata containing line numbers and byte offsets
        at specified intervals. The metadata file is named using the original filename with a `.meta` extension
        and is used for efficient access in checkout and other methods.

        Args:
            buffer_size (int): Size of the buffer for reading the file. Default is 1 MB.

        Returns:
            None. The function writes metadata to a `.meta` file and does not return any value.

        Notes:
            - The interval for metadata points is chosen to balance file size and seek efficiency.
            - Metadata is regenerated if missing or forced in __init__.
            - This method does not modify the original file.
        """

        def _gen(reader: Callable) -> Generator[bytes, None, None]:
            """
            Reads the file in fixed-size chunks, yielding only complete lines and buffering any partial line for the next chunk.

            This function ensures that lines are not split across chunk boundaries, which is crucial for accurate line counting and seeking.
            At the end, any remaining buffer (possibly a partial line) is yielded as the last chunk.

            Args:
                reader (Callable): Function that reads a specified number of bytes from the file.

            Yields:
                bytes: Chunks containing only complete lines (ending with a newline). The last chunk may contain a partial line.

            Details:
                - If a chunk ends in the middle of a line, the remainder is buffered and prepended to the next chunk.
                - If the file does not end with a newline, the last line is still yielded.
                - Used for efficient processing and metadata generation in large files.
            """
            buffer = b""
            chunk = reader(buffer_size)
            while chunk:
                chunk = buffer + chunk  # Prepend the buffer to the current chunk

                # Find the last newline character in the chunk
                last_newline_index = chunk.rfind(b"\n")
                if last_newline_index != -1:
                    # Yield the complete portion of the chunk
                    yield chunk[: last_newline_index + 1]
                    # Save the remainder to the buffer
                    buffer = chunk[last_newline_index + 1 :]
                else:
                    # If no newline is found, add the entire chunk to the buffer
                    buffer += chunk
                chunk = reader(buffer_size)

            # Yield any remaining buffer as the last chunk
            if buffer:
                yield buffer

        with open(self.filename, "rb") as f:
            line_count = sum(chunk.count(b"\n") for chunk in _gen(f.raw.read))

        # Create index with 1M line intervals for efficient seeking
        # Trade-off: Smaller interval = more metadata, faster seeks
        #            Larger interval = less metadata, slower seeks
        # 1M strikes balance: ~1KB metadata per 1M lines, acceptable seek overhead
        # For 100M line file: 100 index points, ~100KB metadata
        line_interval = min(line_count, 1_000_000)

        # every line interval, get the seek point (x bytes into the file) and line_number
        with open(self.filename, "rb") as f, open(self.meta_filename, "w") as mf:
            line_number = 0
            seek_point = 0

            for chunk in _gen(f.raw.read):
                for line in chunk.splitlines(
                    keepends=True
                ):  # Use splitlines with keepends=True to preserve newline characters
                    line_number += 1
                    seek_point += len(line)

                    if line_number % line_interval == 0:
                        mf.write(f"{line_number},{seek_point}\n")

