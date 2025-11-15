"""
REST API endpoints for IronSwarm dashboard.

Provides endpoints for cluster info, scenario management, metrics, and exports.
"""

import ast
import asyncio
import io
import json
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiohttp import web

import ironswarm.metrics.aggregator as aggregator

from ironswarm.metrics.collector import collector
from ironswarm.metrics.graphs import generate_graphs
from ironswarm.metrics.report import format_report
from ironswarm.metrics_snapshot import MetricsSnapshot
from ironswarm.scenario_discovery import discover_scenarios, ScenarioValidationError

logger = logging.getLogger(__name__)


def json_response(data, status=200):
    """Create JSON response with proper headers."""
    return web.Response(
        text=json.dumps(data, default=str),
        status=status,
        content_type="application/json",
    )


async def get_cluster_info(request: web.Request) -> web.Response:
    """Get cluster topology and node information."""
    node = request.app["node"]

    # Get all nodes from CRDT state
    nodes = []
    if "node_register" in node.state:
        node_register = node.state["node_register"]
        for node_id, node_data in node_register.values():
            nodes.append({
                "identity": node_id,
                "host": node_data.get("host", "unknown"),
                "port": node_data.get("port", 0),
                "is_self": node_id == node.identity,
                "last_seen": node_data.get("timestamp", 0),
            })

    # Sort nodes by identity for consistent ordering
    nodes.sort(key=lambda x: x["identity"])

    # Add index to each node
    for idx, n in enumerate(nodes):
        n["index"] = idx

    return json_response({
        "self": {
            "identity": node.identity,
            "host": node.transport.host if hasattr(node, "transport") else "unknown",
            "port": node.transport.port if hasattr(node, "transport") else 0,
            "index": node.index,
            "running": node.running,
        },
        "nodes": nodes,
        "total_nodes": len(nodes),
        "timestamp": datetime.now().isoformat(),
    })


async def get_scenarios(request: web.Request) -> web.Response:
    """Get active scenarios and their status."""
    node = request.app["node"]
    scenarios = []

    # Get scenarios from CRDT state
    if "scenarios" in node.state:
        scenario_set = node.state["scenarios"]
        for scenario_id, scenario_data in scenario_set.values():
            scenarios.append({
                "id": scenario_id,
                "data": scenario_data,
                "active": True,
            })

    # Get scenario manager info if available
    scenario_managers = []
    if hasattr(node, "scheduler") and hasattr(node.scheduler, "scenario_managers"):
        for idx, sm in enumerate(node.scheduler.scenario_managers):
            scenario_managers.append({
                "index": idx,
                "running": sm.running if hasattr(sm, "running") else False,
                "start_time": sm.start_time if hasattr(sm, "start_time") else 0,
                "journeys": [
                    {
                        "spec": j.spec,
                        "volumemodel": {
                            "target": j.volumemodel.target if j.volumemodel else 0,
                            "duration": getattr(j.volumemodel, "duration", None) if j.volumemodel else None,
                        }
                    }
                    for j in (sm.scenario.journeys if hasattr(sm, "scenario") else [])
                ],
            })

    return json_response({
        "scenarios": scenarios,
        "scenario_managers": scenario_managers,
        "timestamp": datetime.now().isoformat(),
    })


async def post_scenario(request: web.Request) -> web.Response:
    """Deploy a new scenario to the cluster."""
    node = request.app["node"]

    try:
        data = await request.json()

        # Get scenario module spec from request
        scenario_spec = data.get("scenario_spec")
        if not scenario_spec:
            return json_response({
                "error": "Missing required field: scenario_spec",
            }, status=400)

        # Validate scenario_spec format (should be "module:attribute")
        if ":" not in scenario_spec:
            return json_response({
                "error": "Invalid scenario_spec format. Expected 'module:attribute'",
            }, status=400)

        # Check if scenario is already running
        if "scenarios" in node.state and scenario_spec in node.state["scenarios"].keys():
            return json_response({
                "error": f"Scenario {scenario_spec} is already running",
            }, status=409)

        # Add to CRDT state with current timestamp
        init_time = datetime.now().timestamp()
        node.state["scenarios"].add(
            scenario_spec,
            init_time=init_time,
            scenario=scenario_spec,
        )

        # Gossip to other nodes
        await node.update_neighbours()

        # The scheduler will automatically detect and start this scenario
        return json_response({
            "status": "started",
            "scenario_id": scenario_spec,
            "init_time": init_time,
        }, status=201)

    except Exception as e:
        logger.error(f"Failed to deploy scenario: {e}")
        return json_response({
            "error": str(e),
        }, status=400)


async def delete_scenario(request: web.Request) -> web.Response:
    """Stop a running scenario."""
    scenario_id = request.match_info["scenario_id"]
    node = request.app["node"]

    try:
        # Find and stop the scenario manager
        scenario_stopped = False

        if hasattr(node, "scheduler") and hasattr(node.scheduler, "scenario_managers"):
            for sm in node.scheduler.scenario_managers:
                # Check if this scenario manager matches the scenario_id
                if hasattr(sm, "scenario") and hasattr(sm.scenario, "journeys"):
                    # The scenario_id is typically the module spec
                    # We need to find a way to match it to the scenario manager
                    # For now, we'll match based on the first journey spec prefix
                    if scenario_id in node.scheduler.scenarios:
                        sm.running = False
                        if hasattr(sm, "cancel_tasks"):
                            await sm.cancel_tasks()
                        scenario_stopped = True
                        break

        # Remove from CRDT state
        if "scenarios" in node.state and scenario_id in node.state["scenarios"].keys():
            node.state["scenarios"].remove(scenario_id)
            await node.update_neighbours()

        if scenario_stopped or scenario_id not in node.state.get("scenarios", {}).keys():
            return json_response({
                "status": "stopped",
                "scenario_id": scenario_id,
            })
        else:
            return json_response({
                "error": f"Scenario {scenario_id} not found",
            }, status=404)

    except Exception as e:
        logger.error(f"Failed to stop scenario {scenario_id}: {e}")
        return json_response({
            "error": str(e),
        }, status=400)


async def get_scenarios_available(request: web.Request) -> web.Response:
    """Get list of available scenario files that can be loaded."""
    node = request.app["node"]

    try:
        # Discover scenarios in the configured directory
        scenarios = discover_scenarios(node.scenarios_dir)

        return json_response({
            "scenarios": scenarios,
            "scenarios_dir": str(node.scenarios_dir),
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Failed to discover scenarios: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def post_scenario_upload(request: web.Request) -> web.Response:
    """Upload a new scenario Python file."""
    node = request.app["node"]

    try:
        # Get the uploaded file
        reader = await request.multipart()
        file_field = await reader.next()

        if file_field is None:
            return json_response({
                "error": "No file uploaded",
            }, status=400)

        # Validate it's a file field
        if file_field.name != "file":
            return json_response({
                "error": "Expected file field named 'file'",
            }, status=400)

        filename = file_field.filename
        if not filename or not filename.endswith(".py"):
            return json_response({
                "error": "File must be a Python (.py) file",
            }, status=400)

        # Read file content
        file_content = await file_field.read()

        # Create scenarios directory if it doesn't exist
        node.scenarios_dir.mkdir(parents=True, exist_ok=True)

        # Save to a temporary file for validation
        temp_file_path = node.scenarios_dir / f".temp_{filename}"
        final_file_path = node.scenarios_dir / filename

        try:
            # Write to temp file
            temp_file_path.write_bytes(file_content)

            # Validate the scenario file
            from ironswarm.scenario_discovery import validate_scenario_file, get_scenario_metadata, file_path_to_module_spec

            scenario_obj = validate_scenario_file(temp_file_path)
            metadata = get_scenario_metadata(scenario_obj)
            module_spec = file_path_to_module_spec(temp_file_path, node.scenarios_dir.parent)

            # If validation passes, move to final location
            if final_file_path.exists():
                # Overwrite existing file
                final_file_path.unlink()

            temp_file_path.rename(final_file_path)

            return json_response({
                "status": "uploaded",
                "filename": filename,
                "module_spec": module_spec,
                "metadata": metadata,
            })

        except ScenarioValidationError as e:
            # Clean up temp file
            if temp_file_path.exists():
                temp_file_path.unlink()
            return json_response({
                "error": f"Validation failed: {str(e)}",
            }, status=400)

    except Exception as e:
        logger.error(f"Failed to upload scenario: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=500)


async def get_metrics_current(request: web.Request) -> web.Response:
    """
    Get current metrics snapshot.

    Query parameters:
        scope: "node" (default) for this node only, "cluster" for cluster-wide aggregated metrics
    """
    node = request.app["node"]
    scope = request.query.get("scope", "node")

    if scope == "cluster":
        # Get all snapshots from CRDT state
        snapshots = node._get_snapshots_from_crdt()

        # Aggregate cluster-wide metrics
        cluster_snapshot = aggregator.get_cluster_snapshot(snapshots)

        return json_response({
            "scope": "cluster",
            "timestamp": cluster_snapshot["timestamp"],
            "node_count": cluster_snapshot["node_count"],
            "counters": cluster_snapshot.get("counters", {}),
            "histograms": cluster_snapshot.get("histograms", {}),
            "events": cluster_snapshot.get("events", {}),
        })
    else:
        # Get metrics from global collector (don't reset - preserve for multiple clients)
        snapshot = collector.snapshot(reset=False)

        return json_response({
            "scope": "node",
            "node_identity": node.identity,
            "timestamp": snapshot["timestamp"],
            "counters": snapshot.get("counters", {}),
            "histograms": snapshot.get("histograms", {}),
            "events": snapshot.get("events", {}),
        })


async def get_metrics_history(request: web.Request) -> web.Response:
    """
    Get historical metrics over a time window.

    Query parameters:
        start: Start timestamp (unix seconds), optional
        end: End timestamp (unix seconds), optional
        scope: "node" for this node only, "cluster" (default) for cluster-wide
    """
    node = request.app["node"]
    scope = request.query.get("scope", "cluster")

    # Parse time window
    start_timestamp = None
    end_timestamp = None
    if "start" in request.query:
        start_timestamp = int(request.query["start"])
    if "end" in request.query:
        end_timestamp = int(request.query["end"])

    # Get snapshots from CRDT state
    all_snapshots = node._get_snapshots_from_crdt()

    # Filter by node if requested
    if scope == "node":
        all_snapshots = [s for s in all_snapshots if s.node_identity == node.identity]

    # Aggregate for time window
    aggregated = aggregator.query_time_window(
        all_snapshots,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
    )

    return json_response({
        "scope": scope,
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "timestamp": aggregated["timestamp"],
        "node_count": aggregated.get("node_count", 0),
        "counters": aggregated.get("counters", {}),
        "histograms": aggregated.get("histograms", {}),
        "events": aggregated.get("events", {}),
    })


async def post_metrics_snapshot(request: web.Request) -> web.Response:
    """Upload a metrics snapshot for analysis."""
    try:
        data = await request.json()

        # Store snapshot temporarily for analysis
        # In a real implementation, might store in Redis or similar
        request.app["uploaded_snapshot"] = data

        return json_response({
            "status": "uploaded",
            "timestamp": data.get("timestamp"),
        })

    except Exception as e:
        logger.error(f"Failed to upload snapshot: {e}")
        return json_response({
            "error": str(e),
        }, status=400)


async def get_export_report(request: web.Request) -> web.Response:
    """Generate and export text report."""
    try:
        # Get current metrics from global collector
        snapshot = collector.snapshot(reset=False)

        # Generate report
        report_text = format_report(snapshot)

        return web.Response(
            text=report_text,
            content_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="ironswarm_report_{int(datetime.now().timestamp())}.txt"'
            },
        )

    except Exception as e:
        logger.error(f"Failed to generate report: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def get_export_graphs(request: web.Request) -> web.Response:
    """Generate and export graphs as ZIP file."""
    try:
        # Get current metrics from global collector
        snapshot = collector.snapshot(reset=False)

        # Create temporary directory for graphs
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Generate graphs
            await asyncio.get_event_loop().run_in_executor(
                None,
                generate_graphs,
                snapshot,
                str(tmppath),
            )

            # Create ZIP file in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for graph_file in tmppath.glob("*.png"):
                    zip_file.write(graph_file, graph_file.name)

            zip_buffer.seek(0)

            return web.Response(
                body=zip_buffer.read(),
                content_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="ironswarm_graphs_{int(datetime.now().timestamp())}.zip"'
                },
            )

    except Exception as e:
        logger.error(f"Failed to generate graphs: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def get_metrics_per_node(request: web.Request) -> web.Response:
    """
    Get latest metrics for each node in the cluster.

    Returns a breakdown of metrics by node identity.
    """
    node = request.app["node"]

    # Get all snapshots from CRDT state
    all_snapshots = node._get_snapshots_from_crdt()

    # Get per-node snapshots
    per_node = aggregator.get_per_node_snapshots(all_snapshots)

    return json_response({
        "nodes": per_node,
        "node_count": len(per_node),
        "timestamp": datetime.now().timestamp(),
    })


async def get_metrics_cluster_status(request: web.Request) -> web.Response:
    """
    Get cluster metrics status showing snapshot counts and coverage per node.
    """
    node = request.app["node"]

    # Get all snapshots from CRDT state
    all_snapshots = node._get_snapshots_from_crdt()

    # Group by node
    from collections import defaultdict
    node_stats = defaultdict(lambda: {"count": 0, "oldest": None, "newest": None})

    for snapshot in all_snapshots:
        nid = snapshot.node_identity
        stats = node_stats[nid]
        stats["count"] += 1

        if stats["oldest"] is None or snapshot.timestamp < stats["oldest"]:
            stats["oldest"] = snapshot.timestamp
        if stats["newest"] is None or snapshot.timestamp > stats["newest"]:
            stats["newest"] = snapshot.timestamp

    # Convert to list format
    nodes_status = []
    for nid, stats in node_stats.items():
        nodes_status.append({
            "node_identity": nid,
            "snapshot_count": stats["count"],
            "oldest_snapshot": stats["oldest"],
            "newest_snapshot": stats["newest"],
            "is_self": nid == node.identity,
        })

    # Sort by node identity
    nodes_status.sort(key=lambda x: x["node_identity"])

    return json_response({
        "nodes": nodes_status,
        "total_snapshots": len(all_snapshots),
        "timestamp": datetime.now().timestamp(),
    })


async def get_metrics_node(request: web.Request) -> web.Response:
    """
    Get metrics for a specific node.

    Path parameters:
        node_id: Node identity to get metrics for
    """
    node = request.app["node"]
    node_id = request.match_info["node_id"]

    # Get snapshots for this specific node
    all_snapshots = node._get_snapshots_from_crdt()
    snapshots = [s for s in all_snapshots if s.node_identity == node_id]

    if not snapshots:
        return json_response({
            "error": f"No metrics found for node {node_id}",
        }, status=404)

    # Get the latest snapshot for this node
    latest_snapshot = max(snapshots, key=lambda s: s.timestamp)

    return json_response({
        "node_identity": node_id,
        "timestamp": latest_snapshot.timestamp,
        "snapshot_count": len(snapshots),
        "counters": latest_snapshot.snapshot_data.get("counters", {}),
        "histograms": latest_snapshot.snapshot_data.get("histograms", {}),
        "events": latest_snapshot.snapshot_data.get("events", {}),
    })


async def get_datapools(request: web.Request) -> web.Response:
    """Get list of all uploaded datapools."""
    node = request.app["node"]

    try:
        # Get datapools directory
        datapools_dir = node.scenarios_dir.parent / "datapools"

        if not datapools_dir.exists():
            return json_response({
                "datapools": [],
                "datapools_dir": str(datapools_dir),
                "timestamp": datetime.now().isoformat(),
            })

        # List all datapool files (excluding metadata files)
        datapools = []
        for file_path in datapools_dir.iterdir():
            if file_path.is_file() and not file_path.name.startswith('.'):
                # Get file stats
                stats = file_path.stat()

                # Count lines in file
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        line_count = sum(1 for _ in f)
                except Exception:
                    line_count = 0

                # Check if metadata file exists
                meta_file = datapools_dir / f".{file_path.name}.meta"
                has_metadata = meta_file.exists()

                datapools.append({
                    "name": file_path.name,
                    "size": stats.st_size,
                    "line_count": line_count,
                    "created": stats.st_ctime,
                    "modified": stats.st_mtime,
                    "has_metadata": has_metadata,
                })

        # Sort by modified time (most recent first)
        datapools.sort(key=lambda x: x["modified"], reverse=True)

        return json_response({
            "datapools": datapools,
            "datapools_dir": str(datapools_dir),
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        logger.error(f"Failed to list datapools: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def post_datapool_upload(request: web.Request) -> web.Response:
    """Upload a new datapool file."""
    node = request.app["node"]

    try:
        # Get the uploaded file
        reader = await request.multipart()
        file_field = await reader.next()

        if file_field is None:
            return json_response({
                "error": "No file uploaded",
            }, status=400)

        # Validate it's a file field
        if file_field.name != "file":
            return json_response({
                "error": "Expected file field named 'file'",
            }, status=400)

        filename = file_field.filename
        if not filename:
            return json_response({
                "error": "Filename is required",
            }, status=400)

        # Read file content
        file_content = await file_field.read()

        # Create datapools directory if it doesn't exist
        datapools_dir = node.scenarios_dir.parent / "datapools"
        datapools_dir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_path = datapools_dir / filename
        file_path.write_bytes(file_content)

        # Get file stats
        stats = file_path.stat()

        # Count lines in file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                line_count = sum(1 for _ in f)
        except Exception:
            line_count = 0

        return json_response({
            "status": "uploaded",
            "name": filename,
            "size": stats.st_size,
            "line_count": line_count,
            "timestamp": datetime.now().isoformat(),
        }, status=201)

    except Exception as e:
        logger.error(f"Failed to upload datapool: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=500)


async def get_datapool(request: web.Request) -> web.Response:
    """Get information about a specific datapool."""
    node = request.app["node"]
    datapool_name = request.match_info["datapool_name"]

    try:
        datapools_dir = node.scenarios_dir.parent / "datapools"
        file_path = datapools_dir / datapool_name

        if not file_path.exists() or not file_path.is_file():
            return json_response({
                "error": f"Datapool '{datapool_name}' not found",
            }, status=404)

        # Get file stats
        stats = file_path.stat()

        # Count lines in file
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                line_count = sum(1 for _ in f)
        except Exception:
            line_count = 0

        # Check if metadata file exists
        meta_file = datapools_dir / f".{datapool_name}.meta"
        has_metadata = meta_file.exists()

        # Get preview (first 10 lines)
        preview_lines = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for i, line in enumerate(f):
                    if i >= 10:
                        break
                    preview_lines.append(line.rstrip('\n\r'))
        except Exception:
            pass

        return json_response({
            "name": datapool_name,
            "size": stats.st_size,
            "line_count": line_count,
            "created": stats.st_ctime,
            "modified": stats.st_mtime,
            "has_metadata": has_metadata,
            "preview": preview_lines,
        })

    except Exception as e:
        logger.error(f"Failed to get datapool info: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def download_datapool(request: web.Request) -> web.Response:
    """Download a datapool file."""
    node = request.app["node"]
    datapool_name = request.match_info["datapool_name"]

    try:
        datapools_dir = node.scenarios_dir.parent / "datapools"
        file_path = datapools_dir / datapool_name

        if not file_path.exists() or not file_path.is_file():
            return json_response({
                "error": f"Datapool '{datapool_name}' not found",
            }, status=404)

        # Read file content
        file_content = file_path.read_bytes()

        return web.Response(
            body=file_content,
            content_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{datapool_name}"'
            },
        )

    except Exception as e:
        logger.error(f"Failed to download datapool: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def delete_datapool(request: web.Request) -> web.Response:
    """Delete a datapool file."""
    node = request.app["node"]
    datapool_name = request.match_info["datapool_name"]

    try:
        datapools_dir = node.scenarios_dir.parent / "datapools"
        file_path = datapools_dir / datapool_name

        if not file_path.exists() or not file_path.is_file():
            return json_response({
                "error": f"Datapool '{datapool_name}' not found",
            }, status=404)

        # Delete the file
        file_path.unlink()

        # Also delete metadata file if it exists
        meta_file = datapools_dir / f".{datapool_name}.meta"
        if meta_file.exists():
            meta_file.unlink()

        return json_response({
            "status": "deleted",
            "name": datapool_name,
        })

    except Exception as e:
        logger.error(f"Failed to delete datapool: {e}")
        return json_response({
            "error": str(e),
        }, status=500)


async def post_parse_curl(request: web.Request) -> web.Response:
    """Parse a curl command and extract HTTP request details."""
    try:
        data = await request.json()
        curl_command = data.get("curl_command", "")

        if not curl_command:
            return json_response({
                "error": "curl_command is required",
            }, status=400)

        # Basic curl parsing
        import shlex

        parts = shlex.split(curl_command)

        # Initialize parsed data
        parsed = {
            "method": "GET",
            "url": "",
            "headers": {},
            "body": "",
            "query_params": {}
        }

        i = 0
        while i < len(parts):
            part = parts[i]

            # Skip 'curl' command itself
            if part == "curl":
                i += 1
                continue

            # HEAD request
            if part in ["-I", "--head"]:
                parsed["method"] = "HEAD"
                i += 1
                continue

            # Method
            if part in ["-X", "--request"]:
                if i + 1 < len(parts):
                    parsed["method"] = parts[i + 1].upper()
                    i += 2
                    continue

            # Headers
            if part in ["-H", "--header"]:
                if i + 1 < len(parts):
                    header = parts[i + 1]
                    if ":" in header:
                        key, value = header.split(":", 1)
                        parsed["headers"][key.strip()] = value.strip()
                    i += 2
                    continue

            # Data/Body
            if part in ["-d", "--data", "--data-raw", "--data-binary"]:
                if i + 1 < len(parts):
                    parsed["body"] = parts[i + 1]
                    if parsed["method"] == "GET":
                        parsed["method"] = "POST"
                    i += 2
                    continue

            # URL (usually the last non-flag argument)
            if not part.startswith("-") and not parsed["url"]:
                url = part
                # Extract query params from URL
                if "?" in url:
                    base_url, query_string = url.split("?", 1)
                    parsed["url"] = base_url
                    for param in query_string.split("&"):
                        if "=" in param:
                            key, value = param.split("=", 1)
                            parsed["query_params"][key] = value
                else:
                    parsed["url"] = url

            i += 1

        return json_response(parsed)

    except Exception as e:
        logger.error(f"Failed to parse curl command: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=400)


async def post_scenario_builder_save(request: web.Request) -> web.Response:
    """Generate and save a scenario Python file from builder config."""
    node = request.app["node"]

    try:
        config = await request.json()

        # Extract configuration
        scenario_name = config.get("name", "generated_scenario")
        delay = config.get("delay", 0)
        journeys = config.get("journeys", [])
        globals_vars = config.get("globals", [])

        if not journeys:
            return json_response({
                "error": "At least one journey is required",
            }, status=400)

        # Generate Python code
        python_code = _generate_scenario_code(scenario_name, delay, journeys, globals_vars)

        # Save to scenarios directory
        filename = f"{scenario_name}.py"
        file_path = node.scenarios_dir / filename

        file_path.write_text(python_code)

        return json_response({
            "status": "saved",
            "filename": filename,
            "code": python_code,
        }, status=201)

    except Exception as e:
        logger.error(f"Failed to save scenario: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=500)


async def post_scenario_builder_preview(request: web.Request) -> web.Response:
    """Generate Python code preview without saving."""
    try:
        config = await request.json()

        scenario_name = config.get("name", "generated_scenario")
        delay = config.get("delay", 0)
        journeys = config.get("journeys", [])
        globals_vars = config.get("globals", [])

        python_code = _generate_scenario_code(scenario_name, delay, journeys, globals_vars)

        return json_response({
            "code": python_code,
        })

    except Exception as e:
        logger.error(f"Failed to generate preview: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=400)


async def get_scenario_builder_load(request: web.Request) -> web.Response:
    """Load and parse an existing scenario file for editing."""
    node = request.app["node"]
    scenario_name = request.match_info["scenario_name"]

    try:
        # Remove .py extension if provided
        if scenario_name.endswith(".py"):
            scenario_name = scenario_name[:-3]

        file_path = node.scenarios_dir / f"{scenario_name}.py"

        if not file_path.exists():
            return json_response({
                "error": f"Scenario '{scenario_name}' not found",
            }, status=404)

        # Read and parse the file
        code = file_path.read_text()
        parsed_config = _parse_scenario_code(code, scenario_name)

        return json_response(parsed_config)

    except Exception as e:
        logger.error(f"Failed to load scenario: {e}", exc_info=True)
        return json_response({
            "error": str(e),
        }, status=500)


def _parse_scenario_code(code: str, scenario_name: str) -> dict:
    """Parse a scenario Python file and extract configuration."""
    import ast
    import re

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Invalid Python syntax: {e}")

    config = {
        "name": scenario_name,
        "delay": 0,
        "journeys": [],
        "globals": []
    }

    # Extract global variables (module-level assignments)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Skip the scenario assignment itself
                    if target.id == 'scenario':
                        continue

                    # Extract variable name and value
                    var_name = target.id
                    var_value = ""

                    # Try to get the value as a string
                    try:
                        var_value = ast.unparse(node.value)
                    except:
                        if isinstance(node.value, ast.Constant):
                            var_value = str(node.value.value)

                    config["globals"].append({
                        "name": var_name,
                        "value": var_value
                    })

    # Find journey function definitions
    journey_functions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if it has @http_session decorator
            has_decorator = any(
                (isinstance(d, ast.Name) and d.id == 'http_session') or
                (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == 'http_session')
                for d in node.decorator_list
            )
            if has_decorator:
                journey_functions[node.name] = node

    # Find scenario definition
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'scenario':
                    if isinstance(node.value, ast.Call):
                        # Extract delay
                        for keyword in node.value.keywords:
                            if keyword.arg == 'delay':
                                if isinstance(keyword.value, ast.Constant):
                                    config["delay"] = keyword.value.value

                        # Extract journeys
                        for keyword in node.value.keywords:
                            if keyword.arg == 'journeys':
                                if isinstance(keyword.value, ast.List):
                                    for journey_node in keyword.value.elts:
                                        if isinstance(journey_node, ast.Call):
                                            journey_config = _parse_journey_call(journey_node, journey_functions, code)
                                            if journey_config:
                                                config["journeys"].append(journey_config)

    return config


def _parse_journey_call(journey_call: ast.Call, journey_functions: dict, code: str) -> dict:
    """Parse a Journey() call from AST."""
    import ast

    journey_config = {
        "name": "unnamed_journey",
        "requests": [],
        "datapool": None,
        "volumeModel": {"target": 10, "duration": 60}
    }

    # Extract spec (can be positional or keyword argument)
    spec_node = None
    if len(journey_call.args) >= 1:
        spec_node = journey_call.args[0]
    else:
        # Check for spec keyword argument
        for keyword in journey_call.keywords:
            if keyword.arg == 'spec':
                spec_node = keyword.value
                break

    # Extract journey name from spec
    if spec_node:
        if isinstance(spec_node, ast.Constant):
            # String spec like "scenarios.my_scenario:journey_name"
            spec = spec_node.value
            if ':' in spec:
                journey_config["name"] = spec.split(':')[-1]
        elif isinstance(spec_node, ast.Name):
            # Function reference like get_users
            journey_config["name"] = spec_node.id

    # Extract datapool (positional or keyword)
    datapool_node = None
    if len(journey_call.args) >= 2:
        datapool_node = journey_call.args[1]
    else:
        for keyword in journey_call.keywords:
            if keyword.arg == 'datapool':
                datapool_node = keyword.value
                break

    if datapool_node and not (isinstance(datapool_node, ast.Constant) and datapool_node.value is None):
        datapool_config = _parse_datapool_node(datapool_node)
        if datapool_config:
            journey_config["datapool"] = datapool_config

    # Extract volume model (positional or keyword)
    vm_node = None
    if len(journey_call.args) >= 3:
        vm_node = journey_call.args[2]
    else:
        for keyword in journey_call.keywords:
            if keyword.arg == 'volume_model':
                vm_node = keyword.value
                break

    if vm_node and isinstance(vm_node, ast.Call):
        for keyword in vm_node.keywords:
            if keyword.arg == 'target' and isinstance(keyword.value, ast.Constant):
                journey_config["volumeModel"]["target"] = keyword.value.value
            if keyword.arg == 'duration' and isinstance(keyword.value, ast.Constant):
                journey_config["volumeModel"]["duration"] = keyword.value.value

    # Parse journey function body to extract HTTP requests
    journey_name = journey_config["name"]
    if journey_name in journey_functions:
        func_node = journey_functions[journey_name]
        requests = _parse_journey_function(func_node, code)
        journey_config["requests"] = requests

    return journey_config


def _parse_datapool_node(node) -> dict:
    """Parse a datapool constructor call from AST."""
    import ast

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            datapool_type = node.func.id
            source = ""

            # Get source argument
            if len(node.args) >= 1:
                if isinstance(node.args[0], ast.Constant):
                    source = str(node.args[0].value)
                else:
                    # For complex expressions, use ast.unparse if available
                    try:
                        source = ast.unparse(node.args[0])
                    except:
                        source = str(node.args[0])

            return {
                "type": datapool_type,
                "source": source
            }

    return None


def _parse_journey_function(func_node, code: str) -> list:
    """Parse journey function body to extract HTTP requests."""
    import ast
    import re

    requests = []

    # Look for context.session.METHOD(url, ...) patterns in the function
    for node in ast.walk(func_node):
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                if isinstance(item.context_expr, ast.Call):
                    call = item.context_expr
                    # Check if it's context.session.method(...)
                    if isinstance(call.func, ast.Attribute):
                        if isinstance(call.func.value, ast.Attribute):
                            if (isinstance(call.func.value.value, ast.Name) and
                                call.func.value.value.id == 'context' and
                                call.func.value.attr == 'session'):

                                method = call.func.attr.upper()
                                request = {
                                    "method": method,
                                    "url": "",
                                    "headers": {},
                                    "body": "",
                                    "query_params": {}
                                }

                                # Extract URL (first positional arg or url= keyword)
                                if len(call.args) >= 1:
                                    if isinstance(call.args[0], ast.Name) and call.args[0].id == 'url':
                                        # URL is a variable, try to find its assignment
                                        request["url"] = _find_url_assignment(func_node, code)
                                    elif isinstance(call.args[0], ast.Constant):
                                        request["url"] = call.args[0].value
                                    elif isinstance(call.args[0], ast.JoinedStr):
                                        # f-string URL
                                        try:
                                            request["url"] = ast.unparse(call.args[0])
                                        except:
                                            request["url"] = ""

                                # Extract headers from headers= keyword
                                for keyword in call.keywords:
                                    if keyword.arg == 'headers':
                                        if isinstance(keyword.value, ast.Dict):
                                            for k, v in zip(keyword.value.keys, keyword.value.values):
                                                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                                    request["headers"][k.value] = v.value

                                    # Extract query params
                                    if keyword.arg == 'params':
                                        if isinstance(keyword.value, ast.Dict):
                                            for k, v in zip(keyword.value.keys, keyword.value.values):
                                                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                                                    request["query_params"][k.value] = v.value

                                    # Extract JSON body
                                    if keyword.arg == 'json':
                                        try:
                                            request["body"] = ast.unparse(keyword.value)
                                        except:
                                            pass

                                    # Extract data body
                                    if keyword.arg == 'data':
                                        if isinstance(keyword.value, ast.Constant):
                                            request["body"] = keyword.value.value

                                requests.append(request)

    return requests


def _find_url_assignment(func_node, code: str) -> str:
    """Find url variable assignment in function body."""
    import ast

    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'url':
                    if isinstance(node.value, ast.Constant):
                        return node.value.value
                    elif isinstance(node.value, ast.JoinedStr):
                        # f-string - extract the base URL if possible
                        try:
                            return ast.unparse(node.value)
                        except:
                            pass

    return ""


def _generate_scenario_code(scenario_name: str, delay: int, journeys: list, globals_vars: list = None) -> str:
    """Generate Python code for a scenario."""

    # Build imports
    imports = [
        "import asyncio",
        "import os",
        "import random",
        "",
        "from ironswarm.journey.http import http_session",
        "from ironswarm.scenario import Journey, Scenario",
        "from ironswarm.volumemodel import VolumeModel",
    ]

    # Check if any journey uses datapools
    uses_datapools = any(j.get("datapool") for j in journeys)
    if uses_datapools:
        imports.append("from ironswarm.datapools import FileDatapool, IterableDatapool, RecyclableDatapool, RecyclableFileDatapool")

    code_lines = imports + ["", ""]

    # Add global variables
    if globals_vars:
        for var in globals_vars:
            name = var.get("name", "")
            value = var.get("value", "")
            if name and value:
                code_lines.append(f"{name} = {value}")
        code_lines.extend(["", ""])
    else:
        # Add base URL if no globals specified (backward compatibility)
        uses_base_url = any(
            any(req.get("url", "").startswith("http") for req in j.get("requests", []))
            for j in journeys
        )

        if uses_base_url:
            code_lines.extend([
                f'base_url = os.getenv("{scenario_name.upper()}_BASE_URL", "http://127.0.0.1:8080").rstrip("/")',
                "",
                ""
            ])

    # Helper function
    code_lines.extend([
        "def _record_response(context, method: str, url: str, resp) -> None:",
        '    context.log(f"{method} {url} - Status: {resp.status}")',
        "",
        ""
    ])

    # Generate journey functions
    for journey in journeys:
        journey_name = journey.get("name", "unnamed_journey")
        requests = journey.get("requests", [])
        has_datapool = journey.get("datapool") is not None

        # Function signature
        if has_datapool:
            code_lines.append(f"@http_session()")
            code_lines.append(f"async def {journey_name}(context, datapool_item):")
        else:
            code_lines.append(f"@http_session()")
            code_lines.append(f"async def {journey_name}(context):")

        # Generate request code
        if not requests:
            code_lines.append("    pass")
        else:
            for req in requests:
                method = req.get("method", "GET").lower()
                url = req.get("url", "")
                headers = req.get("headers", {})
                body = req.get("body", "")
                query_params = req.get("query_params", {})

                # Build URL
                url_var = f'    url = "{url}"'
                if query_params:
                    params_str = "&".join([f"{k}={v}" for k, v in query_params.items()])
                    url_var = f'    url = "{url}?{params_str}"'
                code_lines.append(url_var)

                # Build request
                request_line = f"    async with context.session.{method}(url"

                # Add headers if present
                if headers:
                    headers_str = ", ".join([f'"{k}": "{v}"' for k, v in headers.items()])
                    request_line += f", headers={{{headers_str}}}"

                # Add body if present
                if body and method in ["post", "put", "patch"]:
                    try:
                        # Try to parse as JSON
                        import json as json_module
                        json_module.loads(body)
                        request_line += f", json={body}"
                    except:
                        request_line += f', data="{body}"'

                request_line += ") as resp:"
                code_lines.append(request_line)
                code_lines.append(f'        _record_response(context, "{method.upper()}", url, resp)')
                code_lines.append("")

        code_lines.append("")

    # Generate scenario definition
    code_lines.append("")
    code_lines.append("scenario = Scenario(")
    code_lines.append("    journeys=[")

    for journey in journeys:
        journey_name = journey.get("name", "unnamed_journey")
        datapool_config = journey.get("datapool")
        volume_model = journey.get("volumeModel", {})

        target = volume_model.get("target", 10)
        duration = volume_model.get("duration", 60)

        # Build datapool part
        if datapool_config:
            dp_type = datapool_config.get("type", "RecyclableDatapool")
            dp_source = datapool_config.get("source", "")

            if dp_type in ["FileDatapool", "RecyclableFileDatapool"]:
                datapool_str = f'{dp_type}("{dp_source}")'
            elif dp_type in ["IterableDatapool", "RecyclableDatapool"]:
                # For iterable, source might be a list
                datapool_str = f'{dp_type}({dp_source})'
            else:
                datapool_str = "None"
        else:
            datapool_str = "None"

        journey_line = f'        Journey("scenarios.{scenario_name}:{journey_name}", {datapool_str}, VolumeModel(target={target}, duration={duration})),'
        code_lines.append(journey_line)

    code_lines.append("    ],")
    code_lines.append(f"    delay={delay},")
    code_lines.append(")")
    code_lines.append("")

    return "\n".join(code_lines)


async def get_debug_state(request: web.Request) -> web.Response:
    """Debug endpoint to view raw node state."""
    node = request.app["node"]

    # Get metrics snapshot stats
    metrics_snapshots = node._get_snapshots_from_crdt() if "metrics_snapshots" in node.state else []

    from collections import defaultdict
    snapshot_stats = defaultdict(int)
    for snapshot in metrics_snapshots:
        snapshot_stats[snapshot.node_identity] += 1

    debug_info = {
        "identity": node.identity,
        "index": node.index,
        "count": node.count,
        "running": node.running,
        "state_keys": list(node.state.keys()),
        "node_register": {
            "keys": list(node.state["node_register"].keys()) if "node_register" in node.state else [],
            "values": [
                {"id": nid, "data": ndata}
                for nid, ndata in node.state["node_register"].values()
            ] if "node_register" in node.state else [],
        },
        "scenarios": {
            "keys": list(node.state["scenarios"].keys()) if "scenarios" in node.state else [],
            "values": [
                {"id": sid, "data": sdata}
                for sid, sdata in node.state["scenarios"].values()
            ] if "scenarios" in node.state else [],
        },
        "metrics_snapshots": {
            "total_count": len(metrics_snapshots),
            "by_node": dict(snapshot_stats),
            "sample": [
                {
                    "node_identity": s.node_identity[:8] + "...",
                    "timestamp": s.timestamp,
                    "age_seconds": s.age_seconds(),
                }
                for s in sorted(metrics_snapshots, key=lambda x: x.timestamp, reverse=True)[:5]
            ],
        },
        "scheduler": {
            "exists": hasattr(node, "scheduler"),
            "has_scenario_managers": hasattr(node, "scheduler") and hasattr(node.scheduler, "scenario_managers"),
            "scenario_managers_count": len(node.scheduler.scenario_managers) if hasattr(node, "scheduler") and hasattr(node.scheduler, "scenario_managers") else 0,
            "scenarios_list": node.scheduler.scenarios if hasattr(node, "scheduler") and hasattr(node.scheduler, "scenarios") else [],
        },
    }

    return json_response(debug_info)


def setup_api_routes(app: web.Application, node, ws_manager):
    """Configure API routes."""
    # Store node reference in app
    app["node"] = node
    app["ws_manager"] = ws_manager

    # API routes
    app.router.add_get("/api/cluster", get_cluster_info)
    app.router.add_get("/api/scenarios", get_scenarios)
    app.router.add_get("/api/scenarios/available", get_scenarios_available)
    app.router.add_post("/api/scenarios", post_scenario)
    app.router.add_post("/api/scenarios/upload", post_scenario_upload)
    app.router.add_delete("/api/scenarios/{scenario_id}", delete_scenario)
    app.router.add_get("/api/metrics/current", get_metrics_current)
    app.router.add_get("/api/metrics/history", get_metrics_history)
    app.router.add_get("/api/metrics/per-node", get_metrics_per_node)
    app.router.add_get("/api/metrics/cluster/status", get_metrics_cluster_status)
    app.router.add_get("/api/metrics/node/{node_id}", get_metrics_node)
    app.router.add_post("/api/metrics/snapshot", post_metrics_snapshot)
    app.router.add_get("/api/export/report", get_export_report)
    app.router.add_get("/api/export/graphs", get_export_graphs)
    app.router.add_get("/api/debug/state", get_debug_state)
    # Datapool routes
    app.router.add_get("/api/datapools", get_datapools)
    app.router.add_post("/api/datapools/upload", post_datapool_upload)
    app.router.add_get("/api/datapools/{datapool_name}", get_datapool)
    app.router.add_get("/api/datapools/{datapool_name}/download", download_datapool)
    app.router.add_delete("/api/datapools/{datapool_name}", delete_datapool)
    # Scenario builder routes
    app.router.add_post("/api/scenario-builder/parse-curl", post_parse_curl)
    app.router.add_post("/api/scenario-builder/save", post_scenario_builder_save)
    app.router.add_post("/api/scenario-builder/preview", post_scenario_builder_preview)
    app.router.add_get("/api/scenario-builder/load/{scenario_name}", get_scenario_builder_load)
