import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from ironswarm.logging_config import configure_logging
from ironswarm.metrics.collector import collector
from ironswarm.node import Node

log = logging.getLogger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-b",
        "--bootstrap",
        help="bootstrap node(s) to initially connect to",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-H",
        "--host",
        help="network interface to bind to local/public or IP address (default: public)",
        type=str,
        default="public",
    )
    parser.add_argument(
        "-p",
        "--port",
        help="port to bind to (default: 42042)",
        type=int,
        default=42042,
    )
    parser.add_argument(
        "-j",
        "--job",
        help="job to run (default: None)",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="enable verbose logging",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "-s",
        "--stats",
        help="enable stats output",
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--log-file", default=None, help="Optional path to write logs to a file."
    )
    parser.add_argument(
        "--metrics-dir",
        help="directory to save periodic metrics snapshots (default: ./metrics/)",
        type=str,
        default="./metrics",
    )
    parser.add_argument(
        "--scenarios-dir",
        help="directory to discover scenario files (default: ./scenarios, or IRONSWARM_SCENARIOS_DIR env var)",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--web-port",
        help="port for web dashboard (default: disabled)",
        type=int,
        default=None,
    )

    return parser.parse_args()


async def async_main():
    """Main async entry point that manages the entire node lifecycle in a single event loop."""
    args = parse_arguments()

    log_level = "DEBUG" if args.verbose else "INFO"
    configure_logging(log_level, log_file=args.log_file)

    # Ensure local modules can be imported
    sys.path.insert(0, os.getcwd())

    bootstrap_nodes = None
    if args.bootstrap:
        bootstrap_nodes = args.bootstrap.split(",")

    # Determine scenarios directory: CLI arg > env var > default
    scenarios_dir = args.scenarios_dir or os.getenv("IRONSWARM_SCENARIOS_DIR", "./scenarios")

    node = Node(
        host=args.host,
        port=args.port,
        bootstrap_nodes=bootstrap_nodes,
        job=args.job,
        output_stats=args.stats,
        web_port=args.web_port,
        metrics_dir=args.metrics_dir,
        scenarios_dir=scenarios_dir,
    )

    await node.bind()
    try:
        await node.run()
    except KeyboardInterrupt:
        log.info("Received shutdown signal...")
    finally:
        await node.shutdown()
        log.info("Node shutdown gracefully.")


def main():
    """CLI entry point - creates and runs the async event loop."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        # asyncio.run handles cleanup, just exit cleanly
        pass


if __name__ == "__main__":
    main()
