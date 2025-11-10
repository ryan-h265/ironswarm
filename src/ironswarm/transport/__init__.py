from ironswarm.lwwelementset import LWWElementSet


class Transport:
    def __init__(self, host: str, port: int, identity: bytes | None = None):
        self.host = host
        self.port = port
        self.identity = identity or b""

    def bind(self):
        """Bind the transport to a port."""
        raise NotImplementedError

    async def listen(self, state: dict[str, LWWElementSet]):
        """Listen for incoming messages."""
        raise NotImplementedError

    async def send(self, node_id, socket, key, state: dict[str, LWWElementSet]):
        """Send a message."""
        raise NotImplementedError

    def close(self):
        """Close the transport."""
        raise NotImplementedError
