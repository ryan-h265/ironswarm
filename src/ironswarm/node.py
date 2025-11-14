from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any, Literal

from ironswarm.helper import ip_address
from ironswarm.lwwelementset import LWWElementSet
from ironswarm.metrics.collector import collector
from ironswarm.metrics_snapshot import MetricsSnapshot
from ironswarm.scheduler import Scheduler
from ironswarm.transport import Transport
from ironswarm.transport.zmq import ZMQTransport
from ironswarm.web import WebServer

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
        web_port: int | None = None,
        metrics_dir: str = "./metrics",
        scenarios_dir: str = "./scenarios",
        metrics_retention_minutes: int = 60,
        metrics_gossip_window_minutes: int = 10,
        metrics_snapshot_ttl_minutes: int = 120,
    ) -> None:
        self.identity: str = uuid.uuid4().hex
        self._index: int | None = None
        self._count: int | None = None
        self._cached_node_keys: set[str] | None = None  # Cache for invalidation detection
        self.state: dict[str, LWWElementSet] = {}
        self.state["node_register"] = LWWElementSet()
        self.state["scenarios"] = LWWElementSet()
        self.state["metrics_snapshots"] = LWWElementSet()
        self.output_stats: bool = output_stats
        self.running: bool = True

        self.scheduler: Scheduler = Scheduler()

        # Metrics configuration
        self.metrics_retention_seconds: int = metrics_retention_minutes * 60
        self.metrics_gossip_window_seconds: int = metrics_gossip_window_minutes * 60
        self.metrics_snapshot_ttl_seconds: int = metrics_snapshot_ttl_minutes * 60

        # Metrics directory setup
        self.metrics_dir: Path = Path(metrics_dir) / self.identity
        self._shared_fs_peers: set[str] = set()  # Peers on same filesystem (detected at bind)

        # Scenarios directory setup
        self.scenarios_dir: Path = Path(scenarios_dir)

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

        # Initialize web server if web_port is provided
        self.web_server: WebServer | None = None
        if web_port:
            self.web_server = WebServer(self, host="0.0.0.0", port=web_port)

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

    def _detect_shared_filesystem_peers(self) -> set[str]:
        """
        Detect peer nodes sharing this filesystem via device ID comparison.

        Nodes on the same filesystem can skip gossiping snapshot JSON and read
        directly from each other's metrics directories.

        Returns:
            Set of node identities (str) that share this node's filesystem
        """
        shared_peers = set()

        try:
            # Get our filesystem's device ID
            my_device = self.metrics_dir.stat().st_dev
            metrics_base = self.metrics_dir.parent

            if not metrics_base.exists():
                return shared_peers

            # Scan for other node directories
            for node_dir in metrics_base.iterdir():
                if not node_dir.is_dir():
                    continue

                # Skip our own directory
                if node_dir.name == self.identity:
                    continue

                try:
                    # Compare device IDs
                    peer_device = node_dir.stat().st_dev
                    if peer_device == my_device:
                        shared_peers.add(node_dir.name)
                        log.debug(
                            f"Detected local filesystem peer: {node_dir.name[:8]}... "
                            f"(same device {my_device})"
                        )
                except (OSError, PermissionError) as e:
                    log.debug(f"Could not stat {node_dir}: {e}")
                    continue

        except (OSError, AttributeError) as e:
            log.warning(f"Failed to detect shared filesystem peers: {e}")

        if shared_peers:
            log.info(
                f"Detected {len(shared_peers)} local filesystem peer(s): "
                f"{[p[:8] + '...' for p in list(shared_peers)[:5]]}"
            )

        return shared_peers

    async def bind(self) -> None:
        """Bind transport and register with bootstrap nodes.

        [TODO] should we bind when we initialize the node
               or use this method to manually bind?
        """
        self.transport.bind()

        # Create metrics directory (parent for all nodes)
        self.metrics_dir.parent.mkdir(parents=True, exist_ok=True)
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Metrics will be saved to {self.metrics_dir}")

        # Load existing snapshots from disk (local + peer)
        self._load_snapshots_from_disk()

        # Detect peers sharing this filesystem (optimization to skip gossiping to them)
        self._shared_fs_peers = self._detect_shared_filesystem_peers()

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
        # Start web server if configured
        if self.web_server:
            await self.web_server.start()

        # Create tasks for concurrent execution
        tasks = [
            asyncio.create_task(self.transport.listen(state=self.state)),
            asyncio.create_task(self.update_loop()),
            asyncio.create_task(self.scheduler.run(self)),
            asyncio.create_task(self.metrics_save_loop()),
            asyncio.create_task(self.peer_snapshot_save_loop()),
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
        """Periodic update loop for neighbor gossip and filesystem peer detection."""
        refresh_counter = 0
        while self.running:
            await self.update_neighbours()

            # Periodically refresh shared filesystem peer detection (every ~60s)
            refresh_counter += 1
            if refresh_counter >= 30:  # 30 iterations * 2s = 60s
                old_peers = self._shared_fs_peers.copy()
                self._shared_fs_peers = self._detect_shared_filesystem_peers()

                # Log if peers changed
                added = self._shared_fs_peers - old_peers
                removed = old_peers - self._shared_fs_peers
                if added:
                    log.info(f"New local filesystem peers detected: {[p[:8] + '...' for p in added]}")
                if removed:
                    log.info(f"Local filesystem peers removed: {[p[:8] + '...' for p in removed]}")

                refresh_counter = 0

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

    async def metrics_save_loop(self) -> None:
        """Periodic metrics snapshot save (every 30s with reset) and CRDT state update."""
        while self.running:
            await asyncio.sleep(30)
            timestamp = int(time())
            snapshot_data = collector.snapshot(reset=True)
            snapshot_data["node_identity"] = self.identity

            # Create MetricsSnapshot for CRDT
            metrics_snapshot = MetricsSnapshot(
                node_identity=self.identity,
                timestamp=timestamp,
                snapshot_data=snapshot_data,
            )

            # Add to CRDT state for gossip using string key
            # Store snapshot data as JSON-serialized metadata
            snapshot_key = f"{self.identity}:{timestamp}"
            self.state["metrics_snapshots"].add(
                snapshot_key,
                timestamp=timestamp,
                node_identity=self.identity,
                snapshot_json=json.dumps(snapshot_data),
            )

            # Save to local disk
            filepath = self.metrics_dir / f"metrics_{timestamp}.json"
            try:
                filepath.write_text(json.dumps(snapshot_data, indent=2), encoding="utf-8")
                log.debug(f"Metrics snapshot saved to {filepath}")
            except Exception as e:
                log.error(f"Failed to save metrics snapshot: {e}")

            # Clean up expired snapshots from CRDT state
            self._cleanup_expired_snapshots()

    async def peer_snapshot_save_loop(self) -> None:
        """Periodic save of peer snapshots to disk for persistence."""
        while self.running:
            await asyncio.sleep(60)  # Save peer snapshots every 60 seconds

            # Get all snapshots from CRDT state
            saved_count = 0
            snapshots = self._get_snapshots_from_crdt()

            for snapshot in snapshots:
                # Skip our own snapshots (already saved in metrics_save_loop)
                if snapshot.node_identity == self.identity:
                    continue

                # Skip local filesystem peers (they write their own files)
                if snapshot.node_identity in self._shared_fs_peers:
                    continue

                # Check if file already exists to avoid redundant writes
                node_dir = self.metrics_dir.parent / snapshot.node_identity
                filepath = node_dir / f"metrics_{snapshot.timestamp}.json"

                if not filepath.exists():
                    self._save_peer_snapshot_to_disk(snapshot)
                    saved_count += 1

            if saved_count > 0:
                log.debug(f"Saved {saved_count} peer snapshots to disk")

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

            # Skip gossiping metrics_snapshots to peers on same filesystem
            # They can read snapshots directly from disk
            if nid in self._shared_fs_peers:
                log.debug(
                    f"Skipping metrics_snapshots gossip to local filesystem peer {nid[:8]}..."
                )
            else:
                log_type(f"sending metrics_snapshots to {nid} {node_socket}")
                await self.transport.send(nid, node_socket, "metrics_snapshots", self.state)

    def _get_snapshots_from_crdt(self) -> list[MetricsSnapshot]:
        """
        Reconstruct MetricsSnapshot objects from CRDT state.

        Returns:
            List of MetricsSnapshot objects
        """
        snapshots = []
        for key, metadata in self.state["metrics_snapshots"].values():
            try:
                # Parse key: "node_identity:timestamp"
                node_identity = metadata.get("node_identity", "")
                timestamp = metadata.get("timestamp", 0)
                snapshot_json = metadata.get("snapshot_json", "{}")

                snapshot_data = json.loads(snapshot_json)

                snapshot = MetricsSnapshot(
                    node_identity=node_identity,
                    timestamp=int(timestamp),
                    snapshot_data=snapshot_data,
                )
                snapshots.append(snapshot)
            except (ValueError, json.JSONDecodeError, KeyError) as e:
                log.warning(f"Failed to reconstruct snapshot from key {key}: {e}")
                continue

        return snapshots

    def _cleanup_expired_snapshots(self) -> None:
        """Remove expired snapshots from CRDT state based on TTL."""
        keys_to_remove = []

        for key, metadata in self.state["metrics_snapshots"].values():
            timestamp = metadata.get("timestamp", 0)
            age = time() - timestamp

            if age > self.metrics_snapshot_ttl_seconds:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.state["metrics_snapshots"].remove(key)
            log.debug(f"Removed expired snapshot: {key}")

    def _load_snapshots_from_disk(self) -> None:
        """Load all snapshots from disk into CRDT state on startup."""
        metrics_base = self.metrics_dir.parent
        loaded_count = 0
        error_count = 0

        # Scan all node directories
        if not metrics_base.exists():
            return

        for node_dir in metrics_base.iterdir():
            if not node_dir.is_dir():
                continue

            node_identity = node_dir.name

            # Load all metrics_*.json files for this node
            for snapshot_file in node_dir.glob("metrics_*.json"):
                try:
                    snapshot_data = json.loads(snapshot_file.read_text(encoding="utf-8"))
                    timestamp = int(snapshot_file.stem.split("_")[1])

                    # Skip expired snapshots
                    age = time() - timestamp
                    if age > self.metrics_snapshot_ttl_seconds:
                        continue

                    # Add to CRDT state using string key
                    snapshot_key = f"{node_identity}:{timestamp}"
                    self.state["metrics_snapshots"].add(
                        snapshot_key,
                        timestamp=timestamp,
                        node_identity=node_identity,
                        snapshot_json=json.dumps(snapshot_data),
                    )
                    loaded_count += 1

                except Exception as e:
                    log.warning(f"Failed to load snapshot {snapshot_file}: {e}")
                    error_count += 1

        log.info(
            f"Loaded {loaded_count} snapshots from disk "
            f"({error_count} errors, skipped expired snapshots)"
        )

    def _save_peer_snapshot_to_disk(self, snapshot: MetricsSnapshot) -> None:
        """Save a peer snapshot to disk for persistence."""
        # Create directory for this node if it doesn't exist
        node_dir = self.metrics_dir.parent / snapshot.node_identity
        node_dir.mkdir(parents=True, exist_ok=True)

        # Save snapshot
        filepath = node_dir / f"metrics_{snapshot.timestamp}.json"
        try:
            filepath.write_text(
                json.dumps(snapshot.snapshot_data, indent=2),
                encoding="utf-8"
            )
            log.debug(
                f"Saved peer snapshot: {snapshot.node_identity[:8]}... "
                f"@ {snapshot.timestamp}"
            )
        except Exception as e:
            log.error(f"Failed to save peer snapshot: {e}")

    def _get_recent_snapshots_for_node(self, node_identity: str | None = None) -> list[MetricsSnapshot]:
        """
        Get recent snapshots for a specific node or all nodes.

        Args:
            node_identity: If provided, filter to this node only. If None, return all.

        Returns:
            List of MetricsSnapshot objects within the gossip window, sorted by timestamp
        """
        current_time = int(time())
        cutoff_time = current_time - self.metrics_gossip_window_seconds

        all_snapshots = self._get_snapshots_from_crdt()

        snapshots = []
        for snapshot in all_snapshots:
            if snapshot.timestamp >= cutoff_time:
                if node_identity is None or snapshot.node_identity == node_identity:
                    snapshots.append(snapshot)

        return sorted(snapshots)

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
        6. Stop web server if running
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

        # Stop web server if configured
        if self.web_server:
            await self.web_server.stop()

        log.info("Node shutdown complete.")
