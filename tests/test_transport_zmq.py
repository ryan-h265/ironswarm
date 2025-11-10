from unittest.mock import AsyncMock, MagicMock

import pytest
import zmq

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.serialization import serialize_lww
from ironswarm.transport.zmq import ZMQTransport


@pytest.fixture
def zmq_transport():
    return ZMQTransport(host="127.0.0.1", port=5555, identity=b"test_identity")


@pytest.fixture
def mock_state():
    return {"key1": LWWElementSet(), "key2": LWWElementSet()}


@pytest.mark.asyncio
async def test_bind(zmq_transport):
    zmq_transport.router = MagicMock()
    zmq_transport.router.bind = MagicMock()

    zmq_transport._bind()

    zmq_transport.router.bind.assert_called_once_with("tcp://127.0.0.1:5555")


@pytest.mark.asyncio
async def test_bind_port_increment(zmq_transport):
    zmq_transport.router = MagicMock()
    zmq_transport.router.bind.side_effect = [
        zmq.error.ZMQError,
        None,
    ]  # Simulate port increment

    zmq_transport.bind()

    assert zmq_transport.port > 5555
    zmq_transport.router.bind.assert_called_with(
        f"tcp://127.0.0.1:{zmq_transport.port}"
    )


def test_close(zmq_transport):
    zmq_transport.router = MagicMock()
    zmq_transport.dealer = MagicMock()
    zmq_transport.context = MagicMock()

    zmq_transport.close()

    zmq_transport.router.close.assert_called_once()
    zmq_transport.dealer.close.assert_called_once()
    zmq_transport.context.term.assert_called_once()


@pytest.mark.asyncio
async def test_listen(zmq_transport, mock_state):
    zmq_transport.router = AsyncMock()
    zmq_transport.router.recv_multipart = AsyncMock(
        side_effect=[
            (b"sender_id", b"", b"key1", serialize_lww(LWWElementSet())),
        ]
    )
    zmq_transport.router.send_multipart = AsyncMock()

    await zmq_transport._listen(mock_state)

    zmq_transport.router.recv_multipart.assert_called()
    zmq_transport.router.send_multipart.assert_called()


@pytest.mark.asyncio
async def test_send(zmq_transport, mock_state):
    zmq_transport.dealer = AsyncMock()
    zmq_transport.dealer.connect = MagicMock()
    zmq_transport.dealer.disconnect = MagicMock()
    zmq_transport.dealer.send_multipart = AsyncMock()
    zmq_transport.dealer.recv_multipart = AsyncMock(
        return_value=(b"", b"key1", serialize_lww(LWWElementSet()))
    )

    await zmq_transport.send("node1", "tcp://127.0.0.1:5555", "key1", mock_state)

    zmq_transport.dealer.connect.assert_called_once_with("tcp://127.0.0.1:5555")
    zmq_transport.dealer.send_multipart.assert_called_once()
    zmq_transport.dealer.recv_multipart.assert_called_once()


@pytest.mark.asyncio
async def test_send_recv_failure(zmq_transport, mock_state):
    zmq_transport.dealer = AsyncMock()
    zmq_transport.dealer.connect = MagicMock()
    zmq_transport.dealer.disconnect = MagicMock()
    zmq_transport.dealer.send_multipart = AsyncMock()
    zmq_transport.dealer.poll = AsyncMock(return_value=0)  # Simulate timeout
    zmq_transport.dealer.recv_multipart = AsyncMock(side_effect=zmq.error.Again())

    await zmq_transport.send("node1", "tcp://127.0.0.1:5555", "key1", mock_state)

    zmq_transport.dealer.connect.assert_called_once_with("tcp://127.0.0.1:5555")
    zmq_transport.dealer.send_multipart.assert_called_once()
    zmq_transport.dealer.poll.assert_called_once_with(2000)
    zmq_transport.dealer.recv_multipart.assert_not_called()  # Ensure recv_multipart is not called due to poll timeout

    # Verify that the node_id was removed from the state
    assert not mock_state["key1"].lookup("node1")
