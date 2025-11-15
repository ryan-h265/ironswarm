"""
Web server for IronSwarm dashboard.

Provides embedded aiohttp web server with REST API and WebSocket support
for real-time monitoring and control of distributed load tests.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

from ironswarm.web.api import setup_api_routes
from ironswarm.web.websocket import WebSocketManager

logger = logging.getLogger(__name__)


class WebServer:
    """Embedded web server for IronSwarm dashboard."""

    def __init__(
        self,
        node,
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        """
        Initialize web server.

        Args:
            node: IronSwarm Node instance to monitor/control
            host: Host to bind to
            port: Port to listen on
        """
        self.node = node
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.ws_manager = WebSocketManager(node)

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Configure web server routes."""
        # API routes
        setup_api_routes(self.app, self.node, self.ws_manager)

        # WebSocket route
        self.app.router.add_get("/ws", self.ws_manager.websocket_handler)

        # Static files (will serve built Vue.js app)
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            self.app.router.add_static("/assets", static_dir / "assets", name="assets")
            self.app.router.add_get("/{tail:.*}", self._serve_index)
        else:
            # Development fallback
            self.app.router.add_get("/", self._dev_placeholder)

    async def _serve_index(self, request: web.Request) -> web.Response:
        """Serve index.html for all routes (SPA routing)."""
        static_dir = Path(__file__).parent / "static"
        index_path = static_dir / "index.html"

        if index_path.exists():
            return web.FileResponse(index_path)
        else:
            return web.Response(
                text="Frontend not built. Run: cd src/ironswarm/web/frontend && npm run build",
                status=503,
            )

    async def _dev_placeholder(self, request: web.Request) -> web.Response:
        """Development placeholder when frontend not built."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>IronSwarm Dashboard</title>
            <style>
                body {
                    margin: 0;
                    padding: 40px;
                    font-family: 'Courier New', monospace;
                    background: #0a0a0a;
                    color: #00ffff;
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                }
                h1 {
                    font-size: 32px;
                    margin-bottom: 20px;
                    text-shadow: 0 0 10px #00ffff;
                }
                .status {
                    padding: 20px;
                    border: 1px solid #00ffff;
                    background: #141414;
                    margin: 20px 0;
                }
                a {
                    color: #ff00ff;
                    text-decoration: none;
                }
                a:hover {
                    text-shadow: 0 0 10px #ff00ff;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⬡ IRONSWARM COMMAND CENTER</h1>
                <div class="status">
                    <p><strong>STATUS:</strong> FRONTEND NOT BUILT</p>
                    <p><strong>NODE:</strong> {node_id}</p>
                    <p><strong>API:</strong> <a href="/api/cluster">/api/cluster</a></p>
                </div>
                <p>Build frontend:</p>
                <pre>cd src/ironswarm/web/frontend && npm install && npm run build</pre>
            </div>
        </body>
        </html>
        """.format(node_id=self.node.identity[:8])
        return web.Response(text=html, content_type="text/html")

    async def start(self):
        """Start the web server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        # Start WebSocket manager background task
        asyncio.create_task(self.ws_manager.broadcast_loop())

        logger.info(f"Web dashboard running at http://{self.host}:{self.port}")

    async def stop(self):
        """Stop the web server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        await self.ws_manager.close_all()
        logger.info("Web dashboard stopped")
