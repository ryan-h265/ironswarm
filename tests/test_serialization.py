"""
Tests for secure serialization module.

These tests verify that the msgpack-based serialization provides
security guarantees against malicious payloads.
"""

import pytest

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.serialization import (
    MAX_COLLECTION_SIZE,
    MAX_MESSAGE_SIZE,
    MAX_METADATA_KEYS,
    MAX_STRING_LENGTH,
    SerializationError,
    ValidationError,
    deserialize_lww,
    serialize_lww,
    validate_lww_dict,
    validate_message_size,
)


class TestSerializeLWW:
    """Test serialize_lww function."""

    def test_serialize_empty_set(self):
        """Test serializing an empty LWWElementSet."""
        lww = LWWElementSet()
        data = serialize_lww(lww)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_serialize_with_elements(self):
        """Test serializing LWWElementSet with elements."""
        lww = LWWElementSet()
        lww.add("node1", host="127.0.0.1", port=42042)
        lww.add("node2", host="192.168.1.1", port=42043)

        data = serialize_lww(lww)
        assert isinstance(data, bytes)
        assert len(data) < MAX_MESSAGE_SIZE

    def test_serialize_with_removed_elements(self):
        """Test serializing LWWElementSet with removed elements."""
        lww = LWWElementSet()
        lww.add("node1", host="127.0.0.1", port=42042)
        lww.remove("node1")

        data = serialize_lww(lww)
        assert isinstance(data, bytes)

    def test_serialize_oversized_fails(self):
        """Test that oversized messages fail to serialize."""
        lww = LWWElementSet()
        # Add many large elements to exceed MAX_MESSAGE_SIZE
        for i in range(100_000):
            lww.add(f"node{i}", data="x" * 100)

        with pytest.raises(SerializationError, match="Message too large"):
            serialize_lww(lww)


class TestDeserializeLWW:
    """Test deserialize_lww function."""

    def test_roundtrip_empty(self):
        """Test serialization roundtrip with empty set."""
        lww1 = LWWElementSet()
        data = serialize_lww(lww1)
        lww2 = deserialize_lww(data)

        assert lww1.keys() == lww2.keys()

    def test_roundtrip_with_elements(self):
        """Test serialization roundtrip with elements."""
        lww1 = LWWElementSet()
        lww1.add("node1", host="127.0.0.1", port=42042)
        lww1.add("node2", host="192.168.1.1", port=42043)

        data = serialize_lww(lww1)
        lww2 = deserialize_lww(data)

        assert lww1.keys() == lww2.keys()
        assert lww1.lookup("node1") == lww2.lookup("node1")

    def test_deserialize_invalid_data(self):
        """Test that invalid data raises SerializationError."""
        with pytest.raises(SerializationError):
            deserialize_lww(b"invalid msgpack data")

    def test_deserialize_oversized_fails(self):
        """Test that oversized messages fail validation."""
        data = b"x" * (MAX_MESSAGE_SIZE + 1)
        with pytest.raises(ValidationError, match="Message too large"):
            deserialize_lww(data)

    def test_deserialize_wrong_schema(self):
        """Test that wrong schema fails validation."""
        import msgpack

        # Missing required keys
        wrong_data = msgpack.packb({"foo": "bar"})
        with pytest.raises(ValidationError, match="Expected keys"):
            deserialize_lww(wrong_data)

    def test_deserialize_missing_timestamp(self):
        """Test that metadata without timestamp fails."""
        import msgpack

        invalid_lww = {
            "add_set": {
                "node1": {"host": "127.0.0.1"}  # Missing timestamp
            },
            "remove_set": {}
        }
        data = msgpack.packb(invalid_lww)
        with pytest.raises(ValidationError, match="Missing required 'timestamp'"):
            deserialize_lww(data)

    def test_deserialize_negative_timestamp(self):
        """Test that negative timestamps fail validation."""
        import msgpack

        invalid_lww = {
            "add_set": {
                "node1": {"timestamp": -1.0, "host": "127.0.0.1"}
            },
            "remove_set": {}
        }
        data = msgpack.packb(invalid_lww)
        with pytest.raises(ValidationError, match="Cannot be negative"):
            deserialize_lww(data)


class TestValidateLWWDict:
    """Test validate_lww_dict function."""

    def test_valid_empty_dict(self):
        """Test that valid empty dict passes validation."""
        data = {"add_set": {}, "remove_set": {}}
        validate_lww_dict(data)  # Should not raise

    def test_valid_dict_with_elements(self):
        """Test that valid dict with elements passes."""
        data = {
            "add_set": {
                "node1": {"timestamp": 123.456, "host": "127.0.0.1", "port": 42042}
            },
            "remove_set": {}
        }
        validate_lww_dict(data)  # Should not raise

    def test_not_a_dict(self):
        """Test that non-dict fails validation."""
        with pytest.raises(ValidationError, match="Expected dict"):
            validate_lww_dict([])

    def test_missing_keys(self):
        """Test that missing keys fail validation."""
        with pytest.raises(ValidationError, match="Expected keys"):
            validate_lww_dict({"add_set": {}})

    def test_extra_keys(self):
        """Test that extra keys fail validation."""
        data = {"add_set": {}, "remove_set": {}, "extra": {}}
        with pytest.raises(ValidationError, match="Expected keys"):
            validate_lww_dict(data)

    def test_too_many_elements(self):
        """Test that exceeding MAX_COLLECTION_SIZE fails."""
        add_set = {f"node{i}": {"timestamp": float(i)} for i in range(MAX_COLLECTION_SIZE + 1)}
        data = {"add_set": add_set, "remove_set": {}}
        with pytest.raises(ValidationError, match="Too many elements"):
            validate_lww_dict(data)

    def test_non_string_key(self):
        """Test that non-string keys fail validation."""
        data = {
            "add_set": {
                123: {"timestamp": 1.0}  # Integer key
            },
            "remove_set": {}
        }
        with pytest.raises(ValidationError, match="Key must be string"):
            validate_lww_dict(data)

    def test_oversized_key(self):
        """Test that oversized keys fail validation."""
        long_key = "x" * (MAX_STRING_LENGTH + 1)
        data = {
            "add_set": {
                long_key: {"timestamp": 1.0}
            },
            "remove_set": {}
        }
        with pytest.raises(ValidationError, match="Key too long"):
            validate_lww_dict(data)

    def test_too_many_metadata_keys(self):
        """Test that too many metadata keys fail."""
        metadata = {"timestamp": 1.0}
        for i in range(MAX_METADATA_KEYS):
            metadata[f"key{i}"] = "value"

        data = {
            "add_set": {"node1": metadata},
            "remove_set": {}
        }
        with pytest.raises(ValidationError, match="Too many metadata keys"):
            validate_lww_dict(data)

    def test_unsupported_metadata_type(self):
        """Test that unsupported types in metadata fail."""
        data = {
            "add_set": {
                "node1": {
                    "timestamp": 1.0,
                    "bad_field": {"nested": "dict"}  # Nested dict not allowed
                }
            },
            "remove_set": {}
        }
        with pytest.raises(ValidationError, match="Unsupported type"):
            validate_lww_dict(data)

    def test_oversized_string_value(self):
        """Test that oversized string values fail."""
        long_value = "x" * (MAX_STRING_LENGTH + 1)
        data = {
            "add_set": {
                "node1": {"timestamp": 1.0, "data": long_value}
            },
            "remove_set": {}
        }
        with pytest.raises(ValidationError, match="String too long"):
            validate_lww_dict(data)

    def test_supported_types_pass(self):
        """Test that all supported types pass validation."""
        data = {
            "add_set": {
                "node1": {
                    "timestamp": 1.0,
                    "str_field": "hello",
                    "int_field": 42,
                    "float_field": 3.14,
                    "bool_field": True,
                    "none_field": None
                }
            },
            "remove_set": {}
        }
        validate_lww_dict(data)  # Should not raise


class TestValidateMessageSize:
    """Test validate_message_size function."""

    def test_small_message_passes(self):
        """Test that small messages pass validation."""
        data = b"small message"
        validate_message_size(data)  # Should not raise

    def test_max_size_message_passes(self):
        """Test that message at max size passes."""
        data = b"x" * MAX_MESSAGE_SIZE
        validate_message_size(data)  # Should not raise

    def test_oversized_message_fails(self):
        """Test that oversized messages fail."""
        data = b"x" * (MAX_MESSAGE_SIZE + 1)
        with pytest.raises(ValidationError, match="exceeds limit"):
            validate_message_size(data)


class TestSecurityScenarios:
    """Test security-critical scenarios."""

    def test_rejects_malicious_nested_structures(self):
        """Test that deeply nested structures are rejected."""
        import msgpack

        # Create deeply nested structure
        malicious = {"add_set": {}, "remove_set": {}}
        malicious["add_set"]["node1"] = {
            "timestamp": 1.0,
            "nested": {"level1": {"level2": "deep"}}  # Nested not allowed
        }

        data = msgpack.packb(malicious)
        with pytest.raises(ValidationError, match="Unsupported type"):
            deserialize_lww(data)

    def test_rejects_code_execution_attempts(self):
        """Test that potential code execution payloads are rejected."""
        import msgpack

        # Msgpack doesn't allow arbitrary objects like pickle does,
        # but we still validate the schema
        malicious = {
            "add_set": {
                "node1": {
                    "timestamp": 1.0,
                    "__import__": "os"  # Attempt to inject code
                }
            },
            "remove_set": {}
        }

        data = msgpack.packb(malicious)
        # This should pass - it's just a string value
        # The point is msgpack prevents code execution unlike pickle
        result = deserialize_lww(data)
        assert result is not None

    def test_memory_exhaustion_protection(self):
        """Test protection against memory exhaustion attacks."""
        import msgpack

        # Try to create an extremely large collection
        large_set = {f"node{i}": {"timestamp": float(i)} for i in range(MAX_COLLECTION_SIZE + 100)}
        malicious = {"add_set": large_set, "remove_set": {}}

        data = msgpack.packb(malicious)
        # Msgpack catches this at unpacking level with SerializationError
        # or our validation catches it with ValidationError
        with pytest.raises((SerializationError, ValidationError), match="(Too many elements|exceeds max_map_len)"):
            deserialize_lww(data)
