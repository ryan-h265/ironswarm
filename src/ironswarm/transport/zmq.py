import logging

import zmq
import zmq.asyncio

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.serialization import (
    SerializationError,
    ValidationError,
    deserialize_lww,
    serialize_lww,
)
from ironswarm.transport import Transport

log = logging.getLogger(__name__)


class ZMQTransport(Transport):
    # Configuration constants
    DEFAULT_POLL_TIMEOUT_MS = 2000  # 2 seconds
    MAX_PORT_BIND_ATTEMPTS = 100

    def __init__(
        self,
        host: str,
        port: int,
        identity: bytes | None = None,
        poll_timeout_ms: int = DEFAULT_POLL_TIMEOUT_MS,
        max_bind_attempts: int = MAX_PORT_BIND_ATTEMPTS,
    ):
        """
        Initialize ZMQ transport.

        Args:
            host: Host address to bind to
            port: Port number to bind to (will increment if unavailable)
            identity: Socket identity for dealer socket
            poll_timeout_ms: Timeout for polling responses in milliseconds
            max_bind_attempts: Maximum number of port increments before failing
        """
        super().__init__(host, port, identity)
        self.context = zmq.asyncio.Context()
        self.router = self.context.socket(zmq.ROUTER)
        self.dealer = self.context.socket(zmq.DEALER)
        self.dealer.setsockopt(zmq.IDENTITY, self.identity)

        # Configuration
        self.poll_timeout_ms = poll_timeout_ms
        self.max_bind_attempts = max_bind_attempts
        self._running = True  # Shutdown flag for listen loop

        # Connection pool: track persistent connections to avoid churn
        self._connected_sockets: set[str] = set()

        # LINGER=0: Discard pending messages immediately on close
        # This is correct for distributed load testing where:
        # - Messages are ephemeral state updates (not critical data)
        # - Fast shutdown is more important than guaranteed delivery
        # - CRDT merge semantics tolerate message loss
        # Trade-off: Fast shutdown vs potential message loss on termination
        self.router.setsockopt(zmq.LINGER, 0)
        self.dealer.setsockopt(zmq.LINGER, 0)

        # ROUTER_HANDOVER: Allow identity takeover on reconnect
        # Enables graceful reconnection when node restarts with same identity
        # http://api.zeromq.org/4-2:zmq-setsockopt#toc42
        self.router.setsockopt(zmq.ROUTER_HANDOVER, 1)

    def bind(self, strict_port: bool = False):
        """
        Bind router socket to host:port.

        Args:
            strict_port: If True, fail immediately if port unavailable.
                        If False, increment port up to max_bind_attempts.

        Raises:
            RuntimeError: If unable to bind after max_bind_attempts
        """
        original_port = self.port
        attempts = 0

        while attempts < self.max_bind_attempts:
            try:
                self._bind()
                if attempts > 0:
                    log.info(f"Bound to {self.host}:{self.port} after {attempts} attempts")
                return
            except zmq.error.ZMQError as e:
                if strict_port:
                    raise RuntimeError(f"Failed to bind to {self.host}:{self.port}: {e}") from e

                attempts += 1
                self.port += 1

        raise RuntimeError(
            f"Failed to bind after {attempts} attempts. "
            f"Tried ports {original_port}-{self.port - 1}"
        )

    def _bind(self):
        self.router.bind(f"tcp://{self.host}:{self.port}")
        log.debug(f"Node {self.identity[:4]} bound to {self.host}:{self.port}")

    async def listen(self, state: dict[str, LWWElementSet]):  # pragma: no cover
        """
        Listen loop for incoming gossip messages.

        Continues until shutdown() is called or unrecoverable error occurs.
        """
        while self._running:
            try:
                await self._listen(state)
            except zmq.error.ZMQError as e:
                if self._running:  # Only log if not intentional shutdown
                    log.exception(f"ZMQ error during listen: {e}")
                break
            except Exception as e:
                log.exception(f"Unexpected error in listen loop: {e}")
                # Continue listening unless it's a critical error
                if not self._running:
                    break

    def shutdown(self):
        """Signal the listen loop to stop gracefully."""
        log.debug("Shutting down ZMQ transport...")
        self._running = False

    async def _listen(self, state: dict[str, LWWElementSet]):
        (
            sender_id,
            _empty,
            key,
            received_data,
        ) = await self.router.recv_multipart()
        log.debug(f"LISTEN: Received message from {sender_id.decode()}")

        # Deserialize with validation
        try:
            received_set = deserialize_lww(received_data)
        except (SerializationError, ValidationError) as e:
            log.error(f"LISTEN: Invalid message from {sender_id.decode()}: {e}")
            # Send empty response to indicate error
            await self.router.send_multipart([sender_id, b"", key, b""])
            return

        key_str = key.decode()

        # Serialize our state
        try:
            serialized_message = serialize_lww(state[key_str])
        except SerializationError as e:
            log.error(f"LISTEN: Failed to serialize state for {key_str}: {e}")
            await self.router.send_multipart([sender_id, b"", key, b""])
            return

        await self.router.send_multipart([sender_id, b"", key, serialized_message])
        log.debug(f"LISTEN: replied to {sender_id.decode()}")

        # merge after reply to reduce b/w
        state[key_str].merge(received_set)

    async def send(self, node_id, socket, key, state: dict[str, LWWElementSet]):
        # Use connection pooling - only connect if not already connected
        if socket not in self._connected_sockets:
            self.dealer.connect(socket)
            self._connected_sockets.add(socket)
            log.debug(f"SEND: New connection to {socket}")

        # Serialize our state
        try:
            serialized_message = serialize_lww(state[key])
        except SerializationError as e:
            log.error(f"SEND: Failed to serialize state for {key}: {e}")
            return

        await self.dealer.send_multipart([b"", key.encode(), serialized_message])
        log.debug(f"SEND: to {node_id} at {socket}")

        # Poll for response with configured timeout
        _event = await self.dealer.poll(self.poll_timeout_ms)
        if _event:
            _empty, _key, received_data = await self.dealer.recv_multipart(zmq.NOBLOCK)
            log.debug(f"SEND: Received response from {node_id} from {socket}")

            # Handle empty response (error from remote)
            if not received_data:
                log.warning(f"SEND: Empty response from {node_id}, likely validation error")
            else:
                # Deserialize with validation
                try:
                    received_set = deserialize_lww(received_data)
                    state[key].merge(received_set)
                except (SerializationError, ValidationError) as e:
                    log.error(f"SEND: Invalid response from {node_id}: {e}")
        else:
            log.warning(f"SEND: No response from {node_id} at {socket}")
            log.warning(f"Failed to swap {key} with {socket}, removing from state?")
            state[key].remove(node_id)
            # Disconnect failed socket and remove from pool
            self.dealer.disconnect(socket)
            self._connected_sockets.discard(socket)
            log.debug(f"SEND: Disconnected failed socket {socket}")

    def close(self):
        log.debug("Closing ZMQTransport...")

        # Disconnect all pooled connections
        for socket in self._connected_sockets:
            try:
                self.dealer.disconnect(socket)
                log.debug(f"Disconnected from {socket}")
            except Exception as e:
                log.warning(f"Error disconnecting from {socket}: {e}")
        self._connected_sockets.clear()

        self.router.close()
        log.debug("Router closed.")
        self.dealer.close()
        log.debug("Dealer closed.")

        self.context.term()
        log.debug("ZMQ context terminated.")
