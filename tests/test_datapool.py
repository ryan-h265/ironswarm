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
