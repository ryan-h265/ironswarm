import pytest

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.transport import Transport


@pytest.fixture
def transport():
    return Transport(host="127.0.0.1", port=5555, identity=b"test_identity")


@pytest.fixture
def mock_state():
    return {"key1": LWWElementSet(), "key2": LWWElementSet()}


def test_bind_raises(transport):
    with pytest.raises(NotImplementedError):
        transport.bind()


@pytest.mark.asyncio
async def test_listen_raises(transport, mock_state):
    with pytest.raises(NotImplementedError):
        await transport.listen(mock_state)


@pytest.mark.asyncio
async def test_send_raises(transport, mock_state):
    with pytest.raises(NotImplementedError):
        await transport.send(1, None, "Key1", mock_state)


def test_close_raises(transport):
    with pytest.raises(NotImplementedError):
        transport.close()
