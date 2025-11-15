import os
import tempfile
import time

import pytest

from ironswarm.datapools import DatapoolBase, FileDatapool, IterableDatapool, RecyclableDatapool, RecyclableFileDatapool

## BASE DATAPOOL

def test_base_datapool_abstraction():
    try:
        _dp = DatapoolBase()
    except TypeError as e:
        assert "Can't instantiate abstract" in str(e)

## ITERABLE DATAPOOL

def test_datapool_initialization():
    data = [1, 2, 3, 4]
    dp = IterableDatapool(data)
    dp_len = len(dp)
    assert dp_len == len(data)
    assert isinstance(dp.uuid, str)

def test_datapool_repr():
    dp = IterableDatapool([1, 2, 3, 4])
    dp_uuid = dp.uuid
    assert repr(dp) == f"Datapool(uuid={dp_uuid}, length=4)"

def test_datapool_checkout():
    data = [1, 2, 3, 4]
    dp = IterableDatapool(data)
    assert next(dp.checkout(start=0, stop=1)) == 1
    assert next(dp.checkout(start=1, stop=2)) == 2

def test_datapool_raise_error_if_not_iter():
    data = 100
    with pytest.raises(TypeError):
        _datapool = IterableDatapool(data)

## RECYCLABLE DATAPOOL

def test_recyclable_datapool_initialization():
    data = [1, 2, 3, 4]
    dp = RecyclableDatapool(data)
    dp_len = len(dp)
    assert dp_len == len(data)
    assert isinstance(dp.uuid, str)

def test_recyclable_datapool_checkout():
    data = [1, 2, 3, 4]
    dp = RecyclableDatapool(data)
    assert next(dp.checkout(start=0, stop=1)) == 1
    assert next(dp.checkout(start=1, stop=2)) == 2
    assert next(dp.checkout(start=4, stop=1)) == 1

## FILE DATAPOOL

def test_file_datapool_initialization():
    # Create a temporary file with sample data
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\n")
        temp_filename = temp_file.name
    try:
        # Call the function to process the file
        file_dp = FileDatapool(temp_filename)

        # Verify the .meta file was created
        assert os.path.exists(file_dp.meta_filename)

        # Verify the contents of the .meta file
        with open(file_dp.meta_filename) as meta_file:
            lines = meta_file.readlines()
            assert len(lines) > 0  # Ensure metadata was written
            assert len(lines[0].split(',')) == 2  # Ensure values are split by ,
    finally:
        # Clean up temporary files
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_seak_closest_point():
    filename = "tests/large_file_test_datapool.txt"
    try:
        file_dp = FileDatapool(filename)
        closest_line_number, closest_seek_point = file_dp._seek_closest_point(1_500_000)
        assert closest_line_number == 1_000_000
        assert closest_seek_point == 6888896
    finally:
        # Clean up temporary files
        os.remove(file_dp.meta_filename)

def test_file_datapool_extract_chunk():
    filename = "tests/large_file_test_datapool.txt"
    try:
        file_dp = FileDatapool(filename)
        result = list(file_dp._extract_chunk(1_500_000, 1_500_003))
        assert result == ["1500001", "1500002", "1500003"]
    finally:
        # Clean up temporary files
        os.remove(file_dp.meta_filename)

def test_file_datapool_checkout():
    # Create a temporary file with sample data
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\n")
        temp_filename = temp_file.name
    try:
        file_dp = FileDatapool(temp_filename)
        result = list(file_dp.checkout(start=1, stop=4))
        assert result == ["Line 2", "Line 3", "Line 4"]
    finally:
        # Clean up temporary files
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

# RECYCLABLE FILE DATAPOOL

def test_recyclable_file_datapool_initialization():
    # Create a temporary file with sample data
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\n")
        temp_filename = temp_file.name
    try:
        # Call the function to process the file
        file_dp = RecyclableFileDatapool(temp_filename)

        # Verify the .meta file was created
        assert os.path.exists(file_dp.meta_filename)

        # Verify the contents of the .meta file
        with open(file_dp.meta_filename) as meta_file:
            lines = meta_file.readlines()
            assert len(lines) > 0  # Ensure metadata was written
            assert len(lines[0].split(',')) == 2  # Ensure values are split by ,
    finally:
        # Clean up temporary files
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_recyclable_file_datapool_checkout():
    # Create a temporary file with sample data
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\n")
        temp_filename = temp_file.name
    try:
        file_dp = RecyclableFileDatapool(temp_filename)
        result = list(file_dp.checkout(start=1, stop=4))
        assert result == ["Line 2", "Line 3", "Line 4"]

        assert next(file_dp.checkout(start=4, stop=1)) == "Line 1"

    finally:
        # Clean up temporary files
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_recyclable_datapool_checkout_stop_zero():
    """Test that stop=0 works correctly with wrap-around in RecyclableDatapool."""
    data = [1, 2, 3, 4, 5]
    dp = RecyclableDatapool(data)
    # checkout(3, 0) should wrap around: items at indices 3, 4
    result = list(dp.checkout(start=3, stop=0))
    assert result == [4, 5]

def test_recyclable_file_datapool_checkout_stop_zero():
    """Test that stop=0 works correctly with wrap-around in RecyclableFileDatapool."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        temp_filename = temp_file.name
    try:
        file_dp = RecyclableFileDatapool(temp_filename)
        # checkout(3, 0) should wrap around: lines at indices 3, 4
        result = list(file_dp.checkout(start=3, stop=0))
        assert result == ["Line 4", "Line 5"]
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_empty_file():
    """Test that FileDatapool handles empty files correctly."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        # Create empty file
        temp_filename = temp_file.name
    try:
        file_dp = FileDatapool(temp_filename)
        assert len(file_dp) == 0
        result = list(file_dp.checkout(start=0, stop=10))
        assert result == []
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_non_utf8_handling():
    """Test that FileDatapool handles non-UTF-8 characters gracefully."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        # Write some valid UTF-8 and some invalid bytes
        temp_file.write(b"Line 1\n")
        temp_file.write(b"Line 2 with invalid \xff\xfe bytes\n")
        temp_file.write(b"Line 3\n")
        temp_filename = temp_file.name
    try:
        file_dp = FileDatapool(temp_filename)
        result = list(file_dp.checkout(start=0, stop=3))
        # Should handle gracefully with replacement characters
        assert len(result) == 3
        assert result[0] == "Line 1"
        # Line 2 will have replacement characters for invalid bytes
        assert "Line 2" in result[1]
        assert result[2] == "Line 3"
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_stale_metadata_detection():
    """Test that FileDatapool regenerates metadata when source file is modified."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\n")
        temp_filename = temp_file.name
    try:
        # Create initial datapool with metadata
        file_dp = FileDatapool(temp_filename)
        assert len(file_dp) == 2
        meta_mtime_before = os.path.getmtime(file_dp.meta_filename)

        # Wait a moment to ensure different timestamps
        time.sleep(0.1)

        # Modify the source file
        with open(temp_filename, "wb") as f:
            f.write(b"Line 1\nLine 2\nLine 3\nLine 4\n")

        # Create new datapool - should detect stale metadata and regenerate
        file_dp2 = FileDatapool(temp_filename)
        assert len(file_dp2) == 4
        meta_mtime_after = os.path.getmtime(file_dp2.meta_filename)

        # Metadata should have been regenerated (newer timestamp)
        assert meta_mtime_after > meta_mtime_before
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_corrupted_metadata_invalid_format():
    """Test that FileDatapool handles corrupted metadata with invalid format."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\n")
        temp_filename = temp_file.name
    try:
        # Create initial datapool with valid metadata
        file_dp = FileDatapool(temp_filename)
        assert len(file_dp) == 3

        # Corrupt the metadata file - invalid format (missing comma)
        with open(file_dp.meta_filename, "w") as mf:
            mf.write("1000 5000\n")  # Should be "1000,5000"
            mf.write("invalid data here\n")

        # Should regenerate metadata instead of crashing
        file_dp2 = FileDatapool(temp_filename)
        assert len(file_dp2) == 3
        result = list(file_dp2.checkout(start=0, stop=3))
        assert result == ["Line 1", "Line 2", "Line 3"]
    finally:
        os.remove(temp_filename)
        if os.path.exists(file_dp.meta_filename):
            os.remove(file_dp.meta_filename)

def test_file_datapool_corrupted_metadata_non_numeric():
    """Test that FileDatapool handles corrupted metadata with non-numeric values."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\n")
        temp_filename = temp_file.name
    try:
        # Create initial datapool
        file_dp = FileDatapool(temp_filename)

        # Corrupt the metadata file - non-numeric values
        with open(file_dp.meta_filename, "w") as mf:
            mf.write("abc,def\n")

        # Should regenerate metadata instead of crashing
        file_dp2 = FileDatapool(temp_filename)
        assert len(file_dp2) == 3
    finally:
        os.remove(temp_filename)
        if os.path.exists(file_dp.meta_filename):
            os.remove(file_dp.meta_filename)

def test_file_datapool_empty_metadata_file():
    """Test that FileDatapool handles empty metadata file."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\n")
        temp_filename = temp_file.name
    try:
        # Create initial datapool
        file_dp = FileDatapool(temp_filename)

        # Make metadata file empty
        with open(file_dp.meta_filename, "w") as mf:
            pass  # Empty file

        # Should regenerate metadata instead of returning 0
        file_dp2 = FileDatapool(temp_filename)
        assert len(file_dp2) == 3
    finally:
        os.remove(temp_filename)
        if os.path.exists(file_dp.meta_filename):
            os.remove(file_dp.meta_filename)

def test_file_datapool_seek_with_corrupted_metadata():
    """Test that _seek_closest_point handles corrupted metadata gracefully."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        temp_filename = temp_file.name
    try:
        # Create initial datapool
        file_dp = FileDatapool(temp_filename)

        # Corrupt the metadata file
        with open(file_dp.meta_filename, "w") as mf:
            mf.write("not,valid,format\n")
            mf.write("still broken\n")

        # Should regenerate and work correctly
        file_dp2 = FileDatapool(temp_filename)
        result = list(file_dp2.checkout(start=2, stop=4))
        assert result == ["Line 3", "Line 4"]
    finally:
        os.remove(temp_filename)
        if os.path.exists(file_dp.meta_filename):
            os.remove(file_dp.meta_filename)

## BOUNDS VALIDATION

def test_iterable_datapool_negative_start():
    """Test that negative start index raises ValueError."""
    dp = IterableDatapool([1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="start must be non-negative"):
        list(dp.checkout(start=-1, stop=3))

def test_iterable_datapool_negative_stop():
    """Test that negative stop index raises ValueError."""
    dp = IterableDatapool([1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="stop must be non-negative"):
        list(dp.checkout(start=0, stop=-1))

def test_iterable_datapool_start_beyond_length():
    """Test that start index beyond datapool length raises ValueError."""
    dp = IterableDatapool([1, 2, 3])
    with pytest.raises(ValueError, match="start index 10 exceeds datapool length 3"):
        list(dp.checkout(start=10, stop=20))

def test_iterable_datapool_start_greater_than_stop():
    """Test that start > stop for non-recyclable datapool raises ValueError."""
    dp = IterableDatapool([1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="stop .* must be >= start .* for non-recyclable"):
        list(dp.checkout(start=4, stop=2))

def test_iterable_datapool_stop_beyond_length_allowed():
    """Test that stop beyond length is allowed and returns available items."""
    dp = IterableDatapool([1, 2, 3])
    result = list(dp.checkout(start=0, stop=100))
    assert result == [1, 2, 3]

def test_file_datapool_negative_start():
    """Test that negative start index raises ValueError for FileDatapool."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\n")
        temp_filename = temp_file.name
    try:
        file_dp = FileDatapool(temp_filename)
        with pytest.raises(ValueError, match="start must be non-negative"):
            list(file_dp.checkout(start=-1, stop=2))
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_file_datapool_start_beyond_length():
    """Test that start beyond length raises ValueError for FileDatapool."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\n")
        temp_filename = temp_file.name
    try:
        file_dp = FileDatapool(temp_filename)
        with pytest.raises(ValueError, match="start index 10 exceeds datapool length 3"):
            list(file_dp.checkout(start=10, stop=20))
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

def test_recyclable_datapool_negative_start():
    """Test that negative start raises ValueError even for recyclable."""
    dp = RecyclableDatapool([1, 2, 3, 4, 5])
    with pytest.raises(ValueError, match="start must be non-negative"):
        list(dp.checkout(start=-1, stop=3))

def test_recyclable_datapool_start_greater_than_stop_wraps():
    """Test that start > stop wraps around for recyclable (no error)."""
    dp = RecyclableDatapool([1, 2, 3, 4, 5])
    # This should NOT raise an error, it should wrap around
    result = list(dp.checkout(start=3, stop=1))
    assert result == [4, 5, 1]

def test_recyclable_file_datapool_start_greater_than_stop_wraps():
    """Test that start > stop wraps around for recyclable file (no error)."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        temp_filename = temp_file.name
    try:
        file_dp = RecyclableFileDatapool(temp_filename)
        # This should NOT raise an error, it should wrap around
        result = list(file_dp.checkout(start=3, stop=1))
        assert result == ["Line 4", "Line 5", "Line 1"]
    finally:
        os.remove(temp_filename)
        os.remove(file_dp.meta_filename)

## MISCELLANEOUS

def test_process_large_data_file_waiting_time():
    filename = "tests/large_file_test_datapool.txt"
    try:
        start_time = time.time()
        # Call the function to process the file
        file_dp = FileDatapool(filename)
        stop_time = time.time()

        # The curent large test file has 2_000_000 of lines
        assert stop_time - start_time < 1.5
    finally:
        # Clean up temporary files
        os.remove(file_dp.meta_filename)

def test_check_cache_large_data_file_waiting_time():
    filename = "tests/large_file_test_datapool.txt"
    try:
        file_dp = FileDatapool(filename)
        # The curent large test file has 2_000_000 of lines
        start_time = time.time()
        len(file_dp)
        stop_time = time.time()
        assert stop_time - start_time < 0.1
    finally:
        # Clean up temporary files
        os.remove(file_dp.meta_filename)
