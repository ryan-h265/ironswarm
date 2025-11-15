"""
WebSocket handler for real-time metrics streaming.

Broadcasts live metrics updates to connected dashboard clients.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Set

import aiohttp
from aiohttp import web

from ironswarm.metrics.collector import collector

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and broadcasts metrics updates."""

    def __init__(self, node):
        """
        Initialize WebSocket manager.

        Args:
            node: IronSwarm Node instance
        """
        self.node = node
        self.clients: Set[web.WebSocketResponse] = set()
        self.running = False

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Add to client set
        self.clients.add(ws)
        logger.info(f"WebSocket client connected (total: {len(self.clients)})")

        try:
            # Send initial state
            await self._send_initial_state(ws)

            # Listen for messages (mostly keep-alive pings)
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # Handle any client messages if needed
                    try:
                        data = json.loads(msg.data)
                        if data.get("type") == "ping":
                            await ws.send_json({"type": "pong"})
                    except json.JSONDecodeError:
                        pass
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")

        finally:
            # Remove from client set
            self.clients.discard(ws)
            logger.info(f"WebSocket client disconnected (remaining: {len(self.clients)})")

        return ws

    async def _send_initial_state(self, ws: web.WebSocketResponse):
        """Send initial cluster and metrics state to new client."""
        try:
            # Send cluster info
            await ws.send_json({
                "type": "cluster_update",
                "data": await self._get_cluster_data(),
            })

            # Send current metrics
            await ws.send_json({
                "type": "metrics_update",
                "data": self._get_metrics_data(),
            })

            # Send scenarios
            await ws.send_json({
                "type": "scenarios_update",
                "data": await self._get_scenarios_data(),
            })

        except Exception as e:
            logger.error(f"Failed to send initial state: {e}")

    async def _get_cluster_data(self):
        """Get cluster topology data."""
        nodes = []
        if "node_register" in self.node.state:
            node_register = self.node.state["node_register"]
            for node_id, node_data in node_register.values():
                nodes.append({
                    "identity": node_id,
                    "host": node_data.get("host", "unknown"),
                    "port": node_data.get("port", 0),
                    "is_self": node_id == self.node.identity,
                })

        nodes.sort(key=lambda x: x["identity"])

        return {
            "self_identity": self.node.identity,
            "nodes": nodes,
            "total_nodes": len(nodes),
            "timestamp": datetime.now().isoformat(),
        }

    def _get_metrics_data(self):
        """Get current metrics snapshot from global collector."""
        # Get metrics from global collector (don't reset - preserve for multiple clients)
        snapshot = collector.snapshot(reset=False)
        return snapshot

    async def _get_scenarios_data(self):
        """Get active scenarios data."""
        scenarios = []

        if hasattr(self.node, "scheduler") and hasattr(self.node.scheduler, "scenario_managers"):
            for idx, sm in enumerate(self.node.scheduler.scenario_managers):
                scenarios.append({
                    "index": idx,
                    "running": sm.running if hasattr(sm, "running") else False,
                })

        return {
            "scenarios": scenarios,
            "timestamp": datetime.now().isoformat(),
        }

    async def broadcast_loop(self):
        """Background task to broadcast metrics updates."""
        self.running = True
        logger.info("WebSocket broadcast loop started")

        while self.running:
            try:
                await asyncio.sleep(2)  # Broadcast every 2 seconds

                if not self.clients:
                    continue

                # Prepare update message
                update = {
                    "type": "metrics_update",
                    "data": self._get_metrics_data(),
                }

                # Broadcast to all connected clients
                disconnected = set()
                for ws in self.clients:
                    try:
                        await ws.send_json(update)
                    except Exception as e:
                        logger.warning(f"Failed to send to client: {e}")
                        disconnected.add(ws)

                # Remove disconnected clients
                self.clients -= disconnected

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}")

        logger.info("WebSocket broadcast loop stopped")

    async def close_all(self):
        """Close all WebSocket connections."""
        self.running = False
        for ws in list(self.clients):
            await ws.close()
        self.clients.clear()
