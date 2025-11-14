"""
Secure serialization module for Iron Swarm wire protocol.

This module replaces unsafe pickle serialization with msgpack + schema validation
to prevent arbitrary code execution attacks from malicious nodes.
"""

import logging
from typing import Any

import msgpack  # type: ignore[import-untyped]

from ironswarm.lwwelementset import LWWElementSet

log = logging.getLogger(__name__)

# Security limits
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB max message size
MAX_COLLECTION_SIZE = 100_000  # Max items in add_set/remove_set
MAX_METADATA_KEYS = 50  # Max keys in metadata dict
MAX_STRING_LENGTH = 10 * 1024  # 10KB - Allow for metrics snapshots with histogram data


class SerializationError(Exception):
    """Raised when serialization/deserialization fails."""


class ValidationError(Exception):
    """Raised when schema validation fails."""


def validate_lww_dict(data: Any, context: str = "root") -> None:
    """
    Validate LWWElementSet dictionary structure.

    Args:
        data: Data to validate
        context: Context string for error messages

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError(f"{context}: Expected dict, got {type(data).__name__}")

    # Must have exactly these keys
    required_keys = {"add_set", "remove_set"}
    if set(data.keys()) != required_keys:
        raise ValidationError(
            f"{context}: Expected keys {required_keys}, got {set(data.keys())}"
        )

    # Validate each set
    for set_name in ["add_set", "remove_set"]:
        validate_element_set(data[set_name], f"{context}.{set_name}")


def validate_element_set(data: Any, context: str) -> None:
    """
    Validate an element set (add_set or remove_set).

    Args:
        data: Data to validate
        context: Context string for error messages

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError(f"{context}: Expected dict, got {type(data).__name__}")

    if len(data) > MAX_COLLECTION_SIZE:
        raise ValidationError(
            f"{context}: Too many elements ({len(data)} > {MAX_COLLECTION_SIZE})"
        )

    for key, value in data.items():
        # Validate key
        if not isinstance(key, str):
            raise ValidationError(
                f"{context}[{key!r}]: Key must be string, got {type(key).__name__}"
            )

        if len(key) > MAX_STRING_LENGTH:
            raise ValidationError(
                f"{context}[{key!r}]: Key too long ({len(key)} > {MAX_STRING_LENGTH})"
            )

        # Validate value (metadata dict)
        validate_metadata(value, f"{context}[{key!r}]")


def validate_metadata(data: Any, context: str) -> None:
    """
    Validate metadata dictionary.

    Args:
        data: Data to validate
        context: Context string for error messages

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise ValidationError(f"{context}: Expected dict, got {type(data).__name__}")

    if len(data) > MAX_METADATA_KEYS:
        raise ValidationError(
            f"{context}: Too many metadata keys ({len(data)} > {MAX_METADATA_KEYS})"
        )

    # Must have timestamp
    if "timestamp" not in data:
        raise ValidationError(f"{context}: Missing required 'timestamp' key")

    # Validate timestamp
    timestamp = data["timestamp"]
    if not isinstance(timestamp, (int, float)):
        raise ValidationError(
            f"{context}.timestamp: Expected number, got {type(timestamp).__name__}"
        )

    if timestamp < 0:
        raise ValidationError(f"{context}.timestamp: Cannot be negative")

    # Validate other metadata values
    for key, value in data.items():
        if key == "timestamp":
            continue

        # Only allow safe types in metadata
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValidationError(
                f"{context}.{key}: Unsupported type {type(value).__name__}"
            )

        # String length limits
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise ValidationError(
                f"{context}.{key}: String too long ({len(value)} > {MAX_STRING_LENGTH})"
            )


def serialize_lww(lww: LWWElementSet) -> bytes:
    """
    Serialize LWWElementSet to msgpack bytes.

    Args:
        lww: LWWElementSet to serialize

    Returns:
        Serialized bytes

    Raises:
        SerializationError: If serialization fails
    """
    try:
        data = lww.to_dict()
        packed = msgpack.packb(data, use_bin_type=True)

        # Check size limit
        if len(packed) > MAX_MESSAGE_SIZE:
            raise SerializationError(
                f"Message too large ({len(packed)} > {MAX_MESSAGE_SIZE})"
            )

        return packed
    except (TypeError, ValueError, OverflowError) as e:
        raise SerializationError(f"Failed to serialize: {e}") from e


def deserialize_lww(data: bytes) -> LWWElementSet:
    """
    Deserialize msgpack bytes to LWWElementSet with validation.

    Args:
        data: Serialized bytes

    Returns:
        Deserialized LWWElementSet

    Raises:
        SerializationError: If deserialization fails
        ValidationError: If schema validation fails
    """
    # Size check before unpacking
    if len(data) > MAX_MESSAGE_SIZE:
        raise ValidationError(
            f"Message too large ({len(data)} > {MAX_MESSAGE_SIZE})"
        )

    try:
        # Unpack with strict limits
        unpacked = msgpack.unpackb(
            data,
            raw=False,  # Decode bytes to str
            strict_map_key=True,  # Only allow str/int keys
            max_bin_len=MAX_MESSAGE_SIZE,  # Max binary data size
            max_str_len=MAX_MESSAGE_SIZE,  # Max string length
            max_array_len=MAX_COLLECTION_SIZE,  # Max array size
            max_map_len=MAX_COLLECTION_SIZE,  # Max map size
        )
    except (msgpack.exceptions.ExtraData,
            msgpack.exceptions.UnpackException,
            ValueError) as e:
        raise SerializationError(f"Failed to deserialize: {e}") from e

    # Validate schema
    validate_lww_dict(unpacked, "LWWElementSet")

    # Construct LWWElementSet
    try:
        return LWWElementSet.from_dict(unpacked)
    except (TypeError, ValueError, KeyError) as e:
        raise SerializationError(f"Failed to construct LWWElementSet: {e}") from e


def validate_message_size(data: bytes) -> None:
    """
    Quick size validation before processing.

    Args:
        data: Data to validate

    Raises:
        ValidationError: If size exceeds limit
    """
    if len(data) > MAX_MESSAGE_SIZE:
        raise ValidationError(
            f"Message size {len(data)} exceeds limit {MAX_MESSAGE_SIZE}"
        )
