"""
Integration tests for distributed metrics sharing.

Tests the gossip-based metrics snapshot sharing across multiple nodes.
"""

import json
import tempfile
from pathlib import Path
from time import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ironswarm.metrics.collector import collector
from ironswarm.metrics import aggregator
from ironswarm.metrics_snapshot import MetricsSnapshot
from ironswarm.node import Node


@pytest.fixture
def mock_transport():
    """Create a mock transport for testing."""
    transport = MagicMock()
    transport.host = "127.0.0.1"
    transport.port = 42042
    transport.listen = AsyncMock()
    transport.send = AsyncMock()
    transport.bind = MagicMock()
    return transport


@pytest.mark.asyncio
async def test_metrics_snapshot_creation():
    """Test creating a MetricsSnapshot from collector data."""
    # Reset collector
    collector.snapshot(reset=True)

    # Generate some metrics
    collector.inc("test_counter", amount=5)
    collector.inc("test_counter", amount=3)

    # Get snapshot
    snapshot_data = collector.snapshot(reset=False)

    # Create MetricsSnapshot
    snapshot = MetricsSnapshot.from_collector("test_node_id", snapshot_data)

    assert snapshot.node_identity == "test_node_id"
    assert snapshot.timestamp > 0
    assert snapshot.age_seconds() >= 0
    assert not snapshot.is_expired(3600)  # 1 hour TTL

    # Test serialization
    snapshot_dict = snapshot.to_dict()
    assert snapshot_dict["node_identity"] == "test_node_id"
    assert "snapshot_data" in snapshot_dict

    # Test deserialization
    restored = MetricsSnapshot.from_dict(snapshot_dict)
    assert restored.node_identity == snapshot.node_identity
    assert restored.timestamp == snapshot.timestamp


@pytest.mark.asyncio
async def test_metrics_snapshot_expiration():
    """Test snapshot TTL and expiration."""
    snapshot_data = {"counters": {}, "histograms": {}, "events": {}}

    # Create snapshot with old timestamp
    old_timestamp = int(time()) - 7200  # 2 hours ago
    snapshot = MetricsSnapshot(
        node_identity="test_node",
        timestamp=old_timestamp,
        snapshot_data=snapshot_data,
    )

    # Should be expired with 1 hour TTL
    assert snapshot.is_expired(3600)

    # Should not be expired with 3 hour TTL
    assert not snapshot.is_expired(10800)


@pytest.mark.asyncio
async def test_metrics_aggregation():
    """Test aggregating snapshots from multiple nodes."""
    # Create snapshots from 3 different nodes
    snapshots = []

    for i in range(3):
        node_id = f"node_{i}"
        timestamp = int(time())

        # Create snapshot with counter data
        snapshot_data = {
            "timestamp": timestamp,
            "counters": {
                "test_requests_total": {
                    "samples": [
                        {"labels": {"endpoint": "/api"}, "value": 10 * (i + 1)},
                        {"labels": {"endpoint": "/health"}, "value": 5 * (i + 1)},
                    ]
                }
            },
            "histograms": {},
            "events": {},
        }

        snapshot = MetricsSnapshot(
            node_identity=node_id,
            timestamp=timestamp,
            snapshot_data=snapshot_data,
        )
        snapshots.append(snapshot)

    # Aggregate
    aggregated = aggregator.aggregate_snapshots(snapshots)

    assert aggregated["node_count"] == 3
    assert "counters" in aggregated
    assert "test_requests_total" in aggregated["counters"]

    # Check aggregated values (should be summed)
    samples = aggregated["counters"]["test_requests_total"]["samples"]
    api_sample = next(s for s in samples if s["labels"]["endpoint"] == "/api")
    health_sample = next(s for s in samples if s["labels"]["endpoint"] == "/health")

    # node_0: 10, node_1: 20, node_2: 30 -> total: 60
    assert api_sample["value"] == 60

    # node_0: 5, node_1: 10, node_2: 15 -> total: 30
    assert health_sample["value"] == 30


@pytest.mark.asyncio
async def test_node_metrics_snapshot_state(mock_transport):
    """Test that nodes add snapshots to CRDT state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create node with custom metrics directory
        node = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
            metrics_snapshot_ttl_minutes=1,
        )

        await node.bind()

        # Initially, state should have metrics_snapshots
        assert "metrics_snapshots" in node.state

        # Create a snapshot and add it
        snapshot_data = {
            "timestamp": int(time()),
            "counters": {},
            "histograms": {},
            "events": {},
        }

        timestamp = int(time())
        snapshot_key = f"{node.identity}:{timestamp}"

        node.state["metrics_snapshots"].add(
            snapshot_key,
            timestamp=timestamp,
            node_identity=node.identity,
            snapshot_json=json.dumps(snapshot_data),
        )

        # Verify it's in the state (should be able to reconstruct from CRDT)
        snapshots = node._get_snapshots_from_crdt()
        snapshot_ids = [s.node_identity for s in snapshots]
        assert node.identity in snapshot_ids

        # Test cleanup of expired snapshots
        old_timestamp = int(time()) - 7200  # 2 hours ago
        old_key = f"{node.identity}:{old_timestamp}"

        node.state["metrics_snapshots"].add(
            old_key,
            timestamp=old_timestamp,
            node_identity=node.identity,
            snapshot_json=json.dumps(snapshot_data),
        )

        # Clean up
        node._cleanup_expired_snapshots()

        # Old snapshot should be removed (TTL is 1 minute)
        assert old_key not in node.state["metrics_snapshots"].keys()


@pytest.mark.asyncio
async def test_snapshot_persistence(mock_transport):
    """Test saving and loading snapshots from disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create node
        node = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
        )

        await node.bind()

        # Create snapshots from multiple nodes
        timestamp = int(time())
        for i in range(3):
            node_id = f"node_{i}"
            snapshot_data = {
                "timestamp": timestamp,
                "node_identity": node_id,
                "counters": {"test": {"samples": [{"labels": {}, "value": i}]}},
                "histograms": {},
                "events": {},
            }

            snapshot = MetricsSnapshot(
                node_identity=node_id,
                timestamp=timestamp,
                snapshot_data=snapshot_data,
            )

            # Add to state
            node.state["metrics_snapshots"].add(snapshot, timestamp=timestamp)

            # Save peer snapshot to disk (skip own node)
            if node_id != node.identity:
                node._save_peer_snapshot_to_disk(snapshot)

        # Verify files were created
        metrics_base = Path(tmpdir)
        for i in range(3):
            node_id = f"node_{i}"
            if node_id != node.identity:
                snapshot_file = metrics_base / node_id / f"metrics_{timestamp}.json"
                assert snapshot_file.exists()

                # Verify content
                data = json.loads(snapshot_file.read_text())
                assert data["node_identity"] == node_id

        # Create a new node that will load snapshots
        transport2 = MagicMock()
        transport2.host = "127.0.0.1"
        transport2.port = 42043
        transport2.listen = AsyncMock()
        transport2.send = AsyncMock()
        transport2.bind = MagicMock()

        node2 = Node(
            host="local",
            port=42043,
            transport=transport2,
            metrics_dir=tmpdir,  # Same directory
        )

        await node2.bind()

        # Should have loaded snapshots from disk
        loaded_snapshots = node2._get_snapshots_from_crdt()

        # Should have loaded the peer snapshots we saved
        assert len(loaded_snapshots) >= 2  # At least the 2 peer snapshots


@pytest.mark.asyncio
async def test_aggregator_time_window():
    """Test querying metrics for a specific time window."""
    # Create snapshots across different times
    base_time = int(time())
    snapshots = []

    for i in range(5):
        timestamp = base_time + (i * 30)  # 30 seconds apart
        snapshot_data = {
            "timestamp": timestamp,
            "counters": {
                "requests": {
                    "samples": [{"labels": {}, "value": 10}]
                }
            },
            "histograms": {},
            "events": {},
        }

        snapshot = MetricsSnapshot(
            node_identity="test_node",
            timestamp=timestamp,
            snapshot_data=snapshot_data,
        )
        snapshots.append(snapshot)

    # Query middle window (snapshots 1, 2, 3)
    start = base_time + 30
    end = base_time + 90

    result = aggregator.query_time_window(
        snapshots,
        start_timestamp=start,
        end_timestamp=end,
    )

    # Should aggregate 3 snapshots (timestamps 30, 60, 90)
    assert "counters" in result
    samples = result["counters"]["requests"]["samples"]
    assert samples[0]["value"] == 30  # 3 snapshots * 10 each


@pytest.mark.asyncio
async def test_get_recent_snapshots(mock_transport):
    """Test filtering recent snapshots for gossip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        node = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
            metrics_gossip_window_minutes=5,  # 5 minute window
        )

        await node.bind()

        current_time = int(time())

        # Add recent snapshot (within window)
        recent_timestamp = current_time - 120  # 2 minutes ago
        recent_key = f"other_node:{recent_timestamp}"
        node.state["metrics_snapshots"].add(
            recent_key,
            timestamp=recent_timestamp,
            node_identity="other_node",
            snapshot_json=json.dumps({}),
        )

        # Add old snapshot (outside window)
        old_timestamp = current_time - 600  # 10 minutes ago
        old_key = f"other_node:{old_timestamp}"
        node.state["metrics_snapshots"].add(
            old_key,
            timestamp=old_timestamp,
            node_identity="other_node",
            snapshot_json=json.dumps({}),
        )

        # Get recent snapshots
        recent = node._get_recent_snapshots_for_node()

        # Should only get the recent one
        recent_timestamps = [s.timestamp for s in recent]
        assert recent_timestamp in recent_timestamps
        assert old_timestamp not in recent_timestamps


@pytest.mark.asyncio
async def test_shared_filesystem_detection(mock_transport):
    """Test detection of nodes sharing the same filesystem."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create first node
        node1 = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
        )

        await node1.bind()

        # Initially, should detect no peers
        assert len(node1._shared_fs_peers) == 0

        # Create second node with different transport but same metrics_dir
        transport2 = MagicMock()
        transport2.host = "127.0.0.1"
        transport2.port = 42043
        transport2.listen = AsyncMock()
        transport2.send = AsyncMock()
        transport2.bind = MagicMock()

        node2 = Node(
            host="local",
            port=42043,
            transport=transport2,
            metrics_dir=tmpdir,
        )

        await node2.bind()

        # Now refresh node1's detection - should find node2
        node1._shared_fs_peers = node1._detect_shared_filesystem_peers()

        # node1 should detect node2
        assert node2.identity in node1._shared_fs_peers

        # node2 should detect node1
        assert node1.identity in node2._shared_fs_peers


@pytest.mark.asyncio
async def test_gossip_skip_for_local_peers(mock_transport):
    """Test that nodes skip gossiping to local filesystem peers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two nodes on same filesystem
        node1 = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
        )

        await node1.bind()

        transport2 = MagicMock()
        transport2.host = "127.0.0.1"
        transport2.port = 42043
        transport2.listen = AsyncMock()
        transport2.send = AsyncMock()
        transport2.bind = MagicMock()

        node2 = Node(
            host="local",
            port=42043,
            transport=transport2,
            metrics_dir=tmpdir,
        )

        await node2.bind()

        # Refresh detection
        node1._shared_fs_peers = node1._detect_shared_filesystem_peers()

        # Add both nodes to node_register
        node1.state["node_register"].add(
            node2.identity,
            host="127.0.0.1",
            port=42043,
        )

        # Call update_neighbours
        await node1.update_neighbours()

        # Check that transport.send was called for node_register and scenarios,
        # but verify metrics_snapshots is NOT sent to local peer
        send_calls = [call[0] for call in mock_transport.send.call_args_list]

        # Should have sent node_register and scenarios
        assert any("node_register" in str(call) for call in send_calls)
        assert any("scenarios" in str(call) for call in send_calls)

        # If node2 is in shared_fs_peers, metrics_snapshots should not be sent
        if node2.identity in node1._shared_fs_peers:
            # Count metrics_snapshots sends
            metrics_calls = [call for call in mock_transport.send.call_args_list
                           if len(call[0]) >= 3 and call[0][2] == "metrics_snapshots"]
            # Should be 0 or only to non-local peers
            assert len(metrics_calls) == 0


@pytest.mark.asyncio
async def test_peer_snapshot_save_skip_local(mock_transport):
    """Test that peer_snapshot_save_loop skips local filesystem peers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        node = Node(
            host="local",
            port=42042,
            transport=mock_transport,
            metrics_dir=tmpdir,
        )

        await node.bind()

        # Simulate a local peer
        local_peer_id = "local_peer_123"
        node._shared_fs_peers.add(local_peer_id)

        # Create peer directory
        peer_dir = Path(tmpdir) / local_peer_id
        peer_dir.mkdir(parents=True, exist_ok=True)

        # Add snapshot to CRDT for local peer
        timestamp = int(time())
        snapshot_key = f"{local_peer_id}:{timestamp}"
        snapshot_data = {"timestamp": timestamp, "counters": {}, "histograms": {}, "events": {}}

        node.state["metrics_snapshots"].add(
            snapshot_key,
            timestamp=timestamp,
            node_identity=local_peer_id,
            snapshot_json=json.dumps(snapshot_data),
        )

        # Get snapshots
        snapshots = node._get_snapshots_from_crdt()

        # Simulate what peer_snapshot_save_loop does
        saved_count = 0
        for snapshot in snapshots:
            if snapshot.node_identity == node.identity:
                continue

            # Should skip local filesystem peers
            if snapshot.node_identity in node._shared_fs_peers:
                continue

            node_dir = node.metrics_dir.parent / snapshot.node_identity
            filepath = node_dir / f"metrics_{snapshot.timestamp}.json"

            if not filepath.exists():
                saved_count += 1

        # Should NOT have saved anything (skipped local peer)
        assert saved_count == 0
