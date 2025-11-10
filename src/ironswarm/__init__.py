import argparse
import asyncio
import logging
import os
import sys

from ironswarm.logging_config import configure_logging
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

    node = Node(
        host=args.host,
        port=args.port,
        bootstrap_nodes=bootstrap_nodes,
        job=args.job,
        output_stats=args.stats,
    )

    await node.bind()
    try:
        await node.run()
    except KeyboardInterrupt:
        log.info("Received shutdown signal...")
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
