"""
REST API endpoints for IronSwarm dashboard.

Provides endpoints for cluster info, scenario management, metrics, and exports.
"""

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
