from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime
from typing import Any, Literal

from ironswarm.helper import ip_address
from ironswarm.journey.http import http_session
from ironswarm.lwwelementset import LWWElementSet
from ironswarm.scheduler import Scheduler
from ironswarm.transport import Transport
from ironswarm.transport.zmq import ZMQTransport

log = logging.getLogger(__name__)


class Node:
    def __init__(
        self,
        host: Literal["public", "local"] | str = "public",
        port: int = 42042,
        bootstrap_nodes: list[str] | None = None,
        transport: Transport | None = None,
        job: str | None = None,
        output_stats: bool = False,
    ) -> None:
        self.identity: str = uuid.uuid4().hex
        self._index: int | None = None
        self._count: int | None = None
        self._cached_node_keys: set[str] | None = None  # Cache for invalidation detection
        self.state: dict[str, LWWElementSet] = {}
        self.state["node_register"] = LWWElementSet()
        self.state["scenarios"] = LWWElementSet()
        self.output_stats: bool = output_stats
        self.running: bool = True

        self.scheduler: Scheduler = Scheduler()

        match host:
            case "public":
                host = ip_address()
            case "local":
                host = "127.0.0.1"

        # Use the provided transport object if available
        self.transport: Transport = transport or ZMQTransport(
            host, port, identity=self.identity.encode()
        )

        self.bootstrap_nodes: list[str] = bootstrap_nodes or []

        if job:
            self.state["scenarios"].add(
                job, init_time=datetime.now().timestamp(), scenario=job,
            )

    def _invalidate_cache(self) -> None:
        """Invalidate cached node index and count when node register changes."""
        current_keys = self.state["node_register"].keys()
        if self._cached_node_keys != current_keys:
            self._cached_node_keys = current_keys.copy()
            self._index = None
            self._count = None

    @property
    def count(self) -> int:
        """Get node count with caching."""
        self._invalidate_cache()
        if self._count is None:
            self._count = len(self._cached_node_keys or set())
        return self._count

    @property
    def index(self) -> int | None:
        """Get node index with caching. O(1) when cache is valid, O(n log n) on invalidation."""
        self._invalidate_cache()
        if self._index is None and self._cached_node_keys:
            # Only sort when cache is invalid
            ordered = sorted(self._cached_node_keys)
            self._index = (
                ordered.index(self.identity) if self.identity in ordered else None
            )
        return self._index

    async def bind(self) -> None:
        """Bind transport and register with bootstrap nodes.

        [TODO] should we bind when we initialize the node
               or use this method to manually bind?
        """
        self.transport.bind()

        self.state["node_register"].add(
            self.identity, host=self.transport.host, port=self.transport.port
        )

        # [TODO] there's an argument to be made that we should
        #        bootstrap when the node is initialized, but
        #        for now we'll do it this way to ensure we send
        #        _this_ nodes information to the bootstrap nodes
        if self.bootstrap_nodes:
            for node in self.bootstrap_nodes:
                log.debug(f"bootstrapping to {node}")
                await self.transport.send(None, node, "node_register", self.state)

    async def run(self) -> None:
        """Run main node event loop.

        Creates and manages concurrent tasks for transport listening, neighbor updates,
        and scenario scheduling. Compatible with Python 3.10+ (TaskGroup added in 3.11).
        """
        # Create tasks for concurrent execution
        tasks = [
            asyncio.create_task(self.transport.listen(state=self.state)),
            asyncio.create_task(self.update_loop()),
            asyncio.create_task(self.scheduler.run(self)),
        ]

        if self.output_stats:
            tasks.append(asyncio.create_task(self.stats()))

        try:
            # Run all tasks concurrently until one fails or all complete
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            # If tasks are cancelled, clean them up gracefully
            for task in tasks:
                if not task.done():
                    task.cancel()
            raise

    async def update_loop(self) -> None:
        """Periodic update loop for neighbor gossip."""
        while self.running:
            await self.update_neighbours()
            await asyncio.sleep(2)

    async def stats(self) -> None:
        """Periodic stats output loop."""
        while self.running:
            msg = f"{self.identity[:4]}:{str(self.transport.port)[-2:]} Node Count:{self.count} Index:{self.index}"
            all_spawned_journeys = 0
            for sc in self.scheduler.scenario_managers:
                all_spawned_journeys += sc.total_spawned_journeys

            msg += f" Journeys Spawned:{all_spawned_journeys}"
            log.info(msg)
            await asyncio.sleep(1)

    def pick_random_neighbours(
        self, id: str, node_list: list[tuple[str, dict[str, Any]]], n: int = 5, exclude_self: bool = True
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Pick random neighbors from node list.

        Args:
            id: This node's identity
            node_list: List of (node_id, metadata) tuples
            n: Number of neighbors to select
            exclude_self: If True, exclude this node from selection

        Returns:
            List of randomly selected neighbors (excluding self if requested)
        """
        if exclude_self:
            node_list = [node for node in node_list if node[0] != id]

        node_list = sorted(node_list)
        if n > len(node_list):
            n = len(node_list)
        return random.sample(node_list, n) if node_list else []

    async def update_neighbours(self, shutting_down: bool = False) -> None:
        """Gossip state updates to random neighbors.

        During normal operation, ensures this node is in the register and sends
        updates to random peers. During shutdown, notifies peers of departure.

        Args:
            shutting_down: If True, skip self-registration and log at info level.
        """
        log_type = log.info if shutting_down else log.debug

        # Re-add self to register if missing (unless shutting down)
        # Note: This recovery mechanism ensures resilience if another node
        # removes us, but requires the shutting_down parameter to prevent
        # re-registration during shutdown.
        if (
            self.identity not in self.state["node_register"].keys()
            and not shutting_down
        ):
            log.debug("Self not found in node register, re-adding.")
            self.state["node_register"].add(
                self.identity, host=self.transport.host, port=self.transport.port
            )

        # Select random neighbors (self excluded automatically)
        neighbours = self.pick_random_neighbours(
            self.identity, self.state["node_register"].values(), n=4, exclude_self=True
        )

        # Gossip state to each neighbor
        # TODO: Expand beyond node_register and scenarios - consider:
        #       - Work assignments
        #       - Performance metrics
        #       - Health status
        for nid, m in neighbours:
            node_socket = f"tcp://{m['host']}:{m['port']}"

            log_type(f"sending node_register to {nid} {node_socket}")
            await self.transport.send(nid, node_socket, "node_register", self.state)
            log_type(f"sending scenarios to {nid} {node_socket}")
            await self.transport.send(nid, node_socket, "scenarios", self.state)

    def show(self) -> None:
        """Display current CRDT state (debug method)."""
        node_register_keys = self.state["node_register"].keys()
        scenarios_keys = self.state["scenarios"].keys()
        log.debug(
            f"Node state - Identity: {self.identity[:8]}... "
            f"Index: {self.index}, Count: {self.count}, "
            f"Registered nodes: {len(node_register_keys)}, "
            f"Active scenarios: {len(scenarios_keys)}"
        )

    async def shutdown(self) -> None:
        """Graceful shutdown sequence.

        1. Stop accepting new work (running=False)
        2. Shutdown scheduler and complete running journeys
        3. Remove self from node register
        4. Notify peers of departure via gossip
        5. Shutdown transport (stops listen loop, closes connections)
        """
        log.info("Shutting down node...")
        self.running = False

        # Gracefully shutdown scheduler and all scenarios
        await self.scheduler.shutdown()

        # Remove self from node register and notify peers
        self.state["node_register"].remove(self.identity)
        await self.update_neighbours(shutting_down=True)

        # Shutdown transport (signals listen loop to stop)
        # Note: shutdown() is available on ZMQTransport but not the base Transport interface
        if hasattr(self.transport, "shutdown"):
            self.transport.shutdown()

        # Close transport sockets
        # Note: HTTP sessions now managed via Context and cleaned up automatically
        self.transport.close()

        log.info("Node shutdown complete.")
