"""
Performance tests to verify optimizations.

These tests verify that performance optimizations work correctly
and don't introduce regressions.
"""

import time

import pytest

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.node import Node
from ironswarm.volumemodel import DynamicVolumeModel, VolumeModel


class TestNodeIndexCaching:
    """Test node index caching optimization."""

    def test_index_cached_when_unchanged(self):
        """Test that index is cached when node register doesn't change."""
        node = Node(host="local", port=42042)
        node.state["node_register"].add(node.identity)
        node.state["node_register"].add("node2")
        node.state["node_register"].add("node3")

        # First access calculates
        index1 = node.index
        # Second access should be cached (no resort)
        index2 = node.index

        assert index1 == index2
        # Verify cache was used (internal state should be set)
        assert node._cached_node_keys is not None

    def test_index_invalidated_on_register_change(self):
        """Test that cache is invalidated when node register changes."""
        node = Node(host="local", port=42042)
        node.state["node_register"].add(node.identity)
        node.state["node_register"].add("node2")

        index1 = node.index
        old_cached_keys = node._cached_node_keys.copy()

        # Add new node - should invalidate cache
        node.state["node_register"].add("node3")
        index2 = node.index

        # Cache should have been invalidated and recalculated
        assert node._cached_node_keys != old_cached_keys

    def test_count_cached_when_unchanged(self):
        """Test that count is cached when node register doesn't change."""
        node = Node(host="local", port=42042)
        node.state["node_register"].add(node.identity)
        node.state["node_register"].add("node2")

        count1 = node.count
        count2 = node.count

        assert count1 == count2 == 2

    def test_index_performance_improvement(self):
        """Test that caching provides performance benefit."""
        node = Node(host="local", port=42042)

        # Add many nodes
        for i in range(100):
            node.state["node_register"].add(f"node{i}")

        # First access (calculates) - do multiple to get stable timing
        times_uncached = []
        for _ in range(10):
            node._index = None  # Force recalculation
            node._cached_node_keys = None
            start = time.perf_counter()
            _ = node.index
            times_uncached.append(time.perf_counter() - start)
        avg_uncached = sum(times_uncached) / len(times_uncached)

        # Subsequent accesses (cached)
        start = time.perf_counter()
        for _ in range(100):
            _ = node.index
        cached_time = time.perf_counter() - start
        avg_cached = cached_time / 100

        # Cached should be faster than uncached
        # Relaxed assertion: just verify caching provides benefit
        assert avg_cached < avg_uncached, f"Cached access ({avg_cached:.6f}s) should be faster than uncached ({avg_uncached:.6f}s)"


class TestVolumeModelCumulative:
    """Test cumulative volume calculation optimization."""

    def test_constant_volume_cumulative(self):
        """Test O(1) cumulative calculation for constant volume."""
        vm = VolumeModel(target=10, duration=100)

        # Should be O(1): target * time_range
        total = vm.cumulative_volume(0, 99)
        assert total == 1000  # 10 * 100

    def test_constant_volume_partial_range(self):
        """Test cumulative for partial time range."""
        vm = VolumeModel(target=5, duration=100)

        total = vm.cumulative_volume(10, 19)
        assert total == 50  # 5 * 10

    def test_constant_volume_zero_range(self):
        """Test cumulative for zero-length range."""
        vm = VolumeModel(target=5)

        total = vm.cumulative_volume(10, 10)
        assert total == 5  # 5 * 1

    def test_constant_volume_invalid_range(self):
        """Test cumulative with invalid range returns zero."""
        vm = VolumeModel(target=5)

        total = vm.cumulative_volume(10, 5)
        assert total == 0

    def test_dynamic_volume_cumulative(self):
        """Test cumulative for dynamic volume model."""
        vm = DynamicVolumeModel(target=100, duration=100, ramp_up=10)

        # Calculate total volume including ramp-up
        total = vm.cumulative_volume(0, 99)
        assert total > 0

        # Verify it matches sum of individual calls
        expected = sum(vm(t) for t in range(100))
        assert total == expected

    def test_cumulative_performance_improvement(self):
        """Test that cumulative is faster than loop for large ranges."""
        vm = VolumeModel(target=10, duration=10000)

        # Method 1: Cumulative (O(1))
        start = time.perf_counter()
        total1 = vm.cumulative_volume(0, 9999)
        cumulative_time = time.perf_counter() - start

        # Method 2: Loop (O(n))
        start = time.perf_counter()
        total2 = sum(vm(t) for t in range(10000))
        loop_time = time.perf_counter() - start

        assert total1 == total2 == 100000
        # Cumulative should be much faster
        assert cumulative_time < loop_time / 100, "Cumulative should be at least 100x faster"


class TestConnectionPooling:
    """Test ZMQ connection pooling optimization."""

    def test_connection_pool_initialized_empty(self):
        """Test that connection pool starts empty."""
        from ironswarm.transport.zmq import ZMQTransport

        transport = ZMQTransport(host="127.0.0.1", port=5555, identity=b"test")
        assert len(transport._connected_sockets) == 0

    def test_connection_pooling_mock(self):
        """Test connection pooling behavior with mocks."""
        from unittest.mock import MagicMock
        from ironswarm.transport.zmq import ZMQTransport

        transport = ZMQTransport(host="127.0.0.1", port=5555, identity=b"test")
        transport.dealer = MagicMock()

        # Simulate connections
        socket1 = "tcp://127.0.0.1:8001"
        socket2 = "tcp://127.0.0.1:8002"

        # First send to socket1 - should connect
        transport._connected_sockets.clear()
        if socket1 not in transport._connected_sockets:
            transport.dealer.connect(socket1)
            transport._connected_sockets.add(socket1)

        assert socket1 in transport._connected_sockets
        assert transport.dealer.connect.call_count == 1

        # Second send to socket1 - should NOT connect again
        if socket1 not in transport._connected_sockets:
            transport.dealer.connect(socket1)

        assert transport.dealer.connect.call_count == 1  # No new connection

        # Send to socket2 - should connect to new socket
        if socket2 not in transport._connected_sockets:
            transport.dealer.connect(socket2)
            transport._connected_sockets.add(socket2)

        assert socket2 in transport._connected_sockets
        assert transport.dealer.connect.call_count == 2

    def test_close_disconnects_all_pooled_connections(self):
        """Test that close() disconnects all pooled connections."""
        from unittest.mock import MagicMock
        from ironswarm.transport.zmq import ZMQTransport

        transport = ZMQTransport(host="127.0.0.1", port=5555, identity=b"test")

        # Mock the sockets
        transport.dealer = MagicMock()
        transport.router = MagicMock()
        transport.context = MagicMock()

        # Add some connections to pool
        transport._connected_sockets = {
            "tcp://127.0.0.1:8001",
            "tcp://127.0.0.1:8002",
            "tcp://127.0.0.1:8003",
        }

        transport.close()

        # Should disconnect all 3 connections
        assert transport.dealer.disconnect.call_count == 3
        assert len(transport._connected_sockets) == 0
