from unittest.mock import AsyncMock, MagicMock

import pytest

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.node import Node


# Ensure all async methods in mock_transport are properly mocked
@pytest.fixture
def mock_transport():
    transport = MagicMock()
    transport.host = "127.0.0.1"
    transport.port = 42042
    transport.listen = AsyncMock()
    transport.send = AsyncMock()  # Ensure send is AsyncMock
    transport.bind = MagicMock()
    return transport


@pytest.fixture
def crdt_sync_node(mock_transport):
    return Node(
        host="local",
        port=42042,
        bootstrap_nodes=["node1", "node2"],
        transport=mock_transport,
        job="test_job",
    )


def test_initialization(crdt_sync_node):
    assert crdt_sync_node.identity is not None
    assert crdt_sync_node.state["node_register"].__class__ == LWWElementSet
    assert crdt_sync_node.state["scenarios"].__class__ == LWWElementSet
    assert crdt_sync_node.running is True


def test_node_count(crdt_sync_node):
    crdt_sync_node.state["node_register"].add("node1")
    crdt_sync_node.state["node_register"].add("node2")
    assert crdt_sync_node.count == 2


def test_node_index(crdt_sync_node):
    crdt_sync_node.state["node_register"].add(crdt_sync_node.identity)
    crdt_sync_node.state["node_register"].add("node1")
    assert crdt_sync_node.index == 0


@pytest.mark.asyncio
async def test_bind(crdt_sync_node):
    await crdt_sync_node.bind()
    crdt_sync_node.transport.bind.assert_called_once()
    assert crdt_sync_node.identity in crdt_sync_node.state["node_register"].keys()


@pytest.mark.asyncio
async def test_update_neighbours(crdt_sync_node):
    crdt_sync_node.state["node_register"].add("node1", host="127.0.0.1", port=42043)
    crdt_sync_node.state["node_register"].add("node2", host="127.0.0.1", port=42044)
    await crdt_sync_node.update_neighbours()
    crdt_sync_node.transport.send.assert_called()


@pytest.mark.asyncio
async def test_shutdown(crdt_sync_node):
    await crdt_sync_node.shutdown()
    assert crdt_sync_node.running is False
    assert crdt_sync_node.identity not in crdt_sync_node.state["node_register"].keys()
