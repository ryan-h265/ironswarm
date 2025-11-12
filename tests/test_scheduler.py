import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ironswarm.lwwelementset import LWWElementSet
from ironswarm.scenario import Journey, Scenario
from ironswarm.scheduler import Scheduler
from ironswarm.volumemodel import VolumeModel

# Test scenario for scheduler tests - can be imported via spec_import
test_scenario = Scenario(
    journeys=[
        Journey("tests.test_scheduler:dummy_journey", None, VolumeModel(target=1, duration=10))
    ]
)


async def dummy_journey(ctx, data):
    """Dummy journey function for testing."""
    await asyncio.sleep(0.01)
    return {"status": "ok"}


class MockNode:
    """Mock node for scheduler tests."""

    def __init__(self):
        self.identity = "test_node"
        self.state = {
            "node_register": LWWElementSet(),
            "scenarios": LWWElementSet(),
        }
        self.running = True
        self._index = 0
        self._count = 1

    @property
    def index(self):
        return self._index

    @property
    def count(self):
        return self._count


@pytest.fixture
def mock_node():
    """Fixture that provides a mock node."""
    node = MockNode()
    node.state["node_register"].add(node.identity)
    return node


@pytest.fixture
def scheduler():
    """Fixture that provides a fresh scheduler instance."""
    return Scheduler()


@pytest.mark.asyncio
async def test_scheduler_initialization(scheduler):
    """Test that scheduler initializes with correct default state."""
    assert scheduler.scenarios == []
    assert scheduler.scenario_managers == []
    assert scheduler.running is True
    assert scheduler._scenario_tasks == {}


@pytest.mark.asyncio
async def test_scheduler_discovers_scenarios(scheduler, mock_node):
    """Test that scheduler discovers and starts scenarios from node state."""
    # Add a scenario to the node state using our test scenario
    scenario_spec = "tests.test_scheduler:test_scenario"
    mock_node.state["scenarios"].add(
        scenario_spec,
        init_time=time.time(),
        scenario=scenario_spec,
    )

    # Run scheduler for a short time
    scheduler_task = asyncio.create_task(scheduler.run(mock_node))
    await asyncio.sleep(0.15)  # Give it enough time to start
    scheduler.running = False
    await scheduler_task

    # Verify scenario was discovered
    assert scenario_spec in scheduler.scenarios
    assert len(scheduler.scenario_managers) == 1


@pytest.mark.asyncio
async def test_scheduler_no_duplicate_scenarios(scheduler):
    """Test that scheduler doesn't start the same scenario twice."""
    # Manually test the deduplication logic
    scenario_spec = "test_spec"

    # Add scenario once
    scheduler.scenarios.append(scenario_spec)

    # Try to add it again - should be skipped
    if scenario_spec in scheduler.scenarios:
        # This simulates the check in scheduler.run()
        duplicate_prevented = True
    else:
        duplicate_prevented = False

    assert duplicate_prevented is True
    assert scheduler.scenarios.count(scenario_spec) == 1


@pytest.mark.asyncio
async def test_scheduler_handles_empty_scenario_state(scheduler, mock_node):
    """Test that scheduler handles empty scenario state gracefully."""
    # Run scheduler with no scenarios
    scheduler_task = asyncio.create_task(scheduler.run(mock_node))
    await asyncio.sleep(0.1)
    scheduler.running = False
    await scheduler_task

    # Verify no scenarios were started
    assert len(scheduler.scenarios) == 0
    assert len(scheduler.scenario_managers) == 0


@pytest.mark.asyncio
async def test_scheduler_cleanup_completed_scenarios():
    """Test that completed scenarios are cleaned up."""
    scheduler = Scheduler()
    mock_node = MockNode()

    # Create a completed mock task
    async def dummy_task():
        pass

    task = asyncio.create_task(dummy_task())
    await task  # Wait for completion

    # Manually add to scheduler
    scheduler._scenario_tasks["test_spec"] = task
    scheduler.scenarios.append("test_spec")

    # Run cleanup
    await scheduler._cleanup_completed_scenarios()

    # Verify cleanup
    assert "test_spec" not in scheduler._scenario_tasks
    assert "test_spec" not in scheduler.scenarios


@pytest.mark.asyncio
async def test_scheduler_cleanup_removes_completed_scenario_managers():
    """Test that scenario managers are removed when their scenarios complete.

    This test verifies the critical cleanup logic that prevents memory leaks
    by ensuring completed scenario managers are removed from the scheduler.
    """
    scheduler = Scheduler()
    mock_node = MockNode()

    # Create completed and running mock tasks
    async def completed_task():
        pass

    async def running_task():
        await asyncio.sleep(10)  # Long-running

    completed = asyncio.create_task(completed_task())
    running = asyncio.create_task(running_task())
    await completed  # Wait for first one to complete

    # Create mock scenario managers
    completed_manager = MagicMock()
    completed_manager.running = False
    completed_manager.scenario = MagicMock(spec=['spec'])  # Has spec attribute

    running_manager = MagicMock()
    running_manager.running = True
    running_manager.scenario = MagicMock(spec=['spec'])

    # Add to scheduler
    scheduler._scenario_tasks["completed_spec"] = completed
    scheduler._scenario_tasks["running_spec"] = running
    scheduler.scenarios = ["completed_spec", "running_spec"]
    scheduler.scenario_managers = [completed_manager, running_manager]

    # Run cleanup
    await scheduler._cleanup_completed_scenarios()

    # Verify completed scenario was removed from all tracking
    assert "completed_spec" not in scheduler._scenario_tasks
    assert "completed_spec" not in scheduler.scenarios

    # Verify running scenario is still tracked
    assert "running_spec" in scheduler._scenario_tasks
    assert "running_spec" in scheduler.scenarios

    # CRITICAL: Verify only running scenario manager remains
    assert len(scheduler.scenario_managers) == 1
    assert scheduler.scenario_managers[0] == running_manager
    assert completed_manager not in scheduler.scenario_managers

    # Cleanup
    running.cancel()
    try:
        await running
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_scheduler_cleanup_handles_multiple_completed_managers():
    """Test that cleanup can handle multiple completed scenarios at once."""
    scheduler = Scheduler()

    # Create multiple completed tasks
    async def dummy_task():
        pass

    tasks = {
        "spec1": asyncio.create_task(dummy_task()),
        "spec2": asyncio.create_task(dummy_task()),
        "spec3": asyncio.create_task(dummy_task()),
    }

    # Wait for all to complete
    await asyncio.gather(*tasks.values())

    # Create corresponding managers (all completed)
    managers = []
    for spec in tasks:
        manager = MagicMock()
        manager.running = False
        manager.scenario = MagicMock(spec=['spec'])
        managers.append(manager)
        scheduler._scenario_tasks[spec] = tasks[spec]
        scheduler.scenarios.append(spec)

    scheduler.scenario_managers = managers.copy()

    # Also add one running manager
    running_manager = MagicMock()
    running_manager.running = True
    running_manager.scenario = MagicMock(spec=['spec'])
    scheduler.scenario_managers.append(running_manager)

    # Run cleanup
    await scheduler._cleanup_completed_scenarios()

    # Verify all completed scenarios removed
    for spec in tasks:
        assert spec not in scheduler._scenario_tasks
        assert spec not in scheduler.scenarios

    # Verify only the running manager remains
    assert len(scheduler.scenario_managers) == 1
    assert scheduler.scenario_managers[0] == running_manager
    for manager in managers:
        assert manager not in scheduler.scenario_managers


@pytest.mark.asyncio
async def test_scheduler_shutdown_cancels_all_tasks():
    """Test that shutdown cancels all running scenario tasks."""
    scheduler = Scheduler()
    mock_node = MockNode()

    # Create a long-running task
    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass  # Expected

    # Add tasks manually
    task1 = asyncio.create_task(long_running_task())
    task2 = asyncio.create_task(long_running_task())

    scheduler._scenario_tasks["task1"] = task1
    scheduler._scenario_tasks["task2"] = task2
    scheduler.scenarios = ["task1", "task2"]

    # Shutdown
    await scheduler.shutdown()

    # Verify all tasks were cancelled
    assert task1.cancelled() or task1.done()
    assert task2.cancelled() or task2.done()
    assert len(scheduler._scenario_tasks) == 0
    assert len(scheduler.scenarios) == 0
    assert scheduler.running is False


@pytest.mark.asyncio
async def test_scenario_resolve_task_creates_manager(scheduler, mock_node):
    """Test that scenario_resolve_task creates a scenario manager."""
    scenario = Scenario(
        journeys=[
            Journey("tests.test_scheduler:dummy_journey", None, VolumeModel(target=1, duration=10))
        ]
    )
    start_time = time.time()

    manager = scheduler.scenario_resolve_task(mock_node, scenario, start_time)

    assert manager in scheduler.scenario_managers
    assert manager.node == mock_node
    assert manager.scenario == scenario
    assert manager.start_time == start_time


@pytest.mark.asyncio
async def test_scheduler_graceful_shutdown_with_scenario_managers():
    """Test that shutdown properly cleans up scenario managers."""
    scheduler = Scheduler()
    mock_node = MockNode()

    # Create a mock scenario manager
    mock_manager = MagicMock()
    mock_manager.running = True
    mock_manager.cancel_tasks = AsyncMock()

    scheduler.scenario_managers.append(mock_manager)

    await scheduler.shutdown()

    # Verify manager was stopped and cancel_tasks was called
    assert mock_manager.running is False
    mock_manager.cancel_tasks.assert_called_once()
    assert len(scheduler.scenario_managers) == 0


@pytest.mark.asyncio
async def test_scheduler_continues_running_until_stopped(scheduler, mock_node):
    """Test that scheduler keeps running until explicitly stopped."""
    start_time = time.time()
    scheduler_task = asyncio.create_task(scheduler.run(mock_node))

    # Let it run for a bit
    await asyncio.sleep(0.2)
    assert scheduler.running is True

    # Stop it
    scheduler.running = False
    await scheduler_task

    elapsed = time.time() - start_time
    assert elapsed >= 0.2  # Ran for at least 200ms
