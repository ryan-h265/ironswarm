"""
Metrics snapshot data structure for distributed sharing.

Represents a single node's metrics snapshot at a specific timestamp,
designed to be shared across the cluster via gossip protocol.
"""

from dataclasses import dataclass
from time import time
from typing import Any


@dataclass(frozen=True)
class MetricsSnapshot:
    """
    Immutable metrics snapshot from a single node at a specific time.

    Attributes:
        node_identity: Unique identifier of the node that created this snapshot
        timestamp: Unix timestamp when the snapshot was created (seconds)
        snapshot_data: The actual metrics data (counters, histograms, events)
    """

    node_identity: str
    timestamp: int
    snapshot_data: dict[str, Any]

    def __hash__(self) -> int:
        """Hash based on node identity and timestamp - naturally unique."""
        return hash((self.node_identity, self.timestamp))

    def __eq__(self, other: object) -> bool:
        """Equality based on node identity and timestamp."""
        if not isinstance(other, MetricsSnapshot):
            return False
        return (self.node_identity == other.node_identity and
                self.timestamp == other.timestamp)

    def __lt__(self, other: "MetricsSnapshot") -> bool:
        """Order by timestamp, then node_identity for consistent sorting."""
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.node_identity < other.node_identity

    def age_seconds(self) -> float:
        """Return age of this snapshot in seconds."""
        return time() - self.timestamp

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if snapshot has exceeded its time-to-live."""
        return self.age_seconds() > ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dictionary for network transmission or storage.

        Returns:
            Dictionary with node_identity, timestamp, and snapshot_data
        """
        return {
            "node_identity": self.node_identity,
            "timestamp": self.timestamp,
            "snapshot_data": self.snapshot_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricsSnapshot":
        """
        Deserialize from dictionary.

        Args:
            data: Dictionary with node_identity, timestamp, and snapshot_data

        Returns:
            MetricsSnapshot instance
        """
        return cls(
            node_identity=data["node_identity"],
            timestamp=data["timestamp"],
            snapshot_data=data["snapshot_data"],
        )

    @classmethod
    def from_collector(cls, node_identity: str, snapshot_data: dict[str, Any]) -> "MetricsSnapshot":
        """
        Create snapshot from collector data with current timestamp.

        Args:
            node_identity: ID of the node creating the snapshot
            snapshot_data: Metrics data from collector.snapshot()

        Returns:
            MetricsSnapshot with current timestamp
        """
        timestamp = int(time())
        return cls(
            node_identity=node_identity,
            timestamp=timestamp,
            snapshot_data=snapshot_data,
        )
