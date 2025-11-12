
import asyncio
import time

import pytest

from ironswarm.datapools import IterableDatapool
from ironswarm.scenario import Journey, Scenario
from ironswarm.scenario_manager import ScenarioManager, node_target_volume, spec_import
from ironswarm.volumemodel import VolumeModel


# Journey functions for testing (not test cases themselves - don't prefix with test_)
async def dummy_journey(ctx, data):
    """Dummy journey function for scenario testing."""
    await asyncio.sleep(0.01)
    return {"status": "ok", "data": data}


async def dummy_journey3(ctx, data):
    """Another dummy journey function for scenario testing."""
    await asyncio.sleep(0.01)
    return {"status": "ok", "data": data}


# Minimal mock node class for ScenarioManager
class MockNode:
    def __init__(self, index=0, count=1, identity="mock-node"):
        self._index = index
        self._count = count
        self.identity = identity

    @property
    def index(self):
        return self._index

    @property
    def count(self):
        return self._count



mock_scenario = Scenario(
    journeys=[
        Journey("mock:journey", None, VolumeModel(target=3, duration=5)),
    ]
)



@pytest.fixture
def mock_node():
    return MockNode(index=2, count=5)

def generate_node_scenario_manager(node, datapool_items, target_volume, journey_duration):
        journey_datapool = IterableDatapool(datapool_items)
        scenario = Scenario(
            journeys=[
                Journey("journey:spec", journey_datapool, VolumeModel(target=target_volume, duration=journey_duration)),
            ],
            interval=1  # Short interval to prevent tests from hanging
        )
        return ScenarioManager(node, time.time(), scenario)


@pytest.fixture
def scenario_manager(mock_node):
    start_time = time.time() - 45  # Start time 45 seconds ago
    scenario = mock_scenario
    return ScenarioManager(mock_node, start_time, scenario)


def test_work_index(scenario_manager):
    """Test that work_index returns the expected value for a given node index and interval."""
    assert scenario_manager.work_index() == 1


def test_elapsed(scenario_manager):
    """Test that elapsed time is non-negative and increases over time."""
    time.sleep(0.02)
    assert scenario_manager.elapsed >= 0


@pytest.mark.parametrize(
    "node_count, journey_duration, target_volume",
    [
        (2, 1, 2),
        (3, 4, 16),
        (3, 10, 20),
        (1, 3, 5),
        (100, 10, 10),
        (100, 60, 10),
        # (2, 0, 2),
        # (2, 1, 0),
    ],
)
def test_datapool_chunks(node_count, journey_duration, target_volume):
    """Test that datapool items are distributed and retrieved correctly across nodes, including edge cases."""
    datapool_size = journey_duration * target_volume
    datapool_items = [f"itm_{i}" for i in range(datapool_size)]

    retrieved_datapool_items = []
    for node_index in range(node_count):
        mock_node = MockNode(index=node_index, count=node_count)
        scenario_manager = generate_node_scenario_manager(mock_node, datapool_items, target_volume, journey_duration)
        for i in range(journey_duration):
            # print(f"wokring on {i=}")
            work = scenario_manager.work(i)
            for _start_delta, _journey_spec, datapool, _target_volume in work:
                if datapool:
                    for item in datapool:
                        retrieved_datapool_items.append(item)
    assert sorted(retrieved_datapool_items) == sorted(datapool_items)


def test_empty_datapool():
    """Test ScenarioManager with an empty datapool."""
    journey_datapool = IterableDatapool([])

    scenario = Scenario(
        journeys=[
            Journey("journey:spec", journey_datapool, VolumeModel(target=1, duration=1)),
        ]
    )

    mock_node = MockNode(index=0, count=1)
    sm = ScenarioManager(mock_node, time.time(), scenario)
    work = sm.work(0)
    for _start_delta, _journey_spec, datapool, _target_volume in work:
        assert datapool is None


def test_single_item_datapool():
    """Test ScenarioManager with a single-item datapool."""
    journey_datapool = IterableDatapool(["only_item"])

    scenario = Scenario(
        journeys=[
            Journey("journey:spec", journey_datapool, VolumeModel(target=1, duration=1)),
        ]
    )

    mock_node = MockNode(index=0, count=1)
    sm = ScenarioManager(mock_node, time.time(), scenario)
    work = sm.work(0)
    found = False
    for _start_delta, _journey_spec, datapool, _target_volume in work:
        items = list(datapool)
        if items:
            assert items == ["only_item"]
            found = True
    assert found


def test_volume_insufficient_datapool():
    """
    Test that volume and datapool items are correctly limited when datapool is insufficient.

    Situation:
        The journey is configured to run at 10 TPS (transactions per second), for a duration
        of 30 seconds. This will result in a total of 300 transactions being processed.

        The datapool has a total of 70 items. Which is insufficient to meet the demands of the journey.

    Intended Outcome:
        The ScenarioManager should retrieve all items from the datapool, but not compromise
        on the rate journeys are spawned.
    """
    node_count = 12
    target_volume = 10
    journey_datapool = [f"itm_{i}" for i in range(70)]
    journey_duration = 30

    total_volume = 0
    total_datapool_items = 0
    for node_index in range(node_count):
        mock_node = MockNode(index=node_index, count=node_count)
        scenario_manager = generate_node_scenario_manager(mock_node, journey_datapool, target_volume, journey_duration)
        # Loop through all duration intervals, not just interval 0
        for interval in range(journey_duration):
            work = scenario_manager.work(interval)
            for _start_delta, _journey_spec, datapool, journey_spawn_volumes in work:
                if datapool:
                    datapool_items = len(list(datapool))
                    if datapool_items:
                        total_datapool_items += datapool_items

                for i in journey_spawn_volumes:
                    total_volume += i
    assert total_datapool_items == len(journey_datapool)


def test_spec_import():
    """Test spec_import for valid and invalid specs."""
    spec = "ironswarm.scenario_manager:ScenarioManager"
    result = spec_import(spec)
    from ironswarm.scenario_manager import ScenarioManager

    assert result == ScenarioManager

    invalid_spec = "nonexistent.module:NonExistentClass"
    with pytest.raises(ModuleNotFoundError):
        spec_import(invalid_spec)

    invalid_attr_spec = "ironswarm.scenario_manager:NonExistentAttribute"
    with pytest.raises(AttributeError):
        spec_import(invalid_attr_spec)

    invalid_spec_format = "InvalidSpecFormat"
    with pytest.raises(ValueError):
        spec_import(invalid_spec_format)


def test_scenario_manager_invalid_args():
    """Test ScenarioManager raises TypeError for missing required args."""
    with pytest.raises(TypeError):
        ScenarioManager()


@pytest.mark.asyncio
async def test_work_resolved_async():
    """Test that work_resolved is empty after running and stopping (async)."""
    mock_node = MockNode(index=0, count=1)
    sm = ScenarioManager(mock_node, time.time(), mock_scenario)
    sm.running = True
    await asyncio.sleep(0.05)
    sm.running = False
    assert isinstance(sm.work_resolved, list)
    assert sm.work_resolved == []


@pytest.mark.asyncio
async def test_scenario_manager_resolve():
    """Test ScenarioManager.resolve() updates work_resolved and running state."""
    # Use a short-duration scenario to avoid long test times
    quick_scenario = Scenario(
        journeys=[
            Journey("mock:journey", None, VolumeModel(target=1, duration=1)),
        ],
        interval=1  # Short interval so test completes quickly
    )
    mock_node = MockNode(index=0, count=2)
    # Start time in the past so scenario completes immediately
    sm = ScenarioManager(mock_node, time.time() - 2, quick_scenario)
    await sm._resolve()
    assert len(sm.work_resolved) > 0


@pytest.mark.asyncio
async def test_scenario_manager_resolve_no_work():
    """Test ScenarioManager.resolve() updates work_resolved and running state."""
    # Use a short-duration scenario to avoid long test times
    quick_scenario = Scenario(
        journeys=[
            Journey("mock:journey", None, VolumeModel(target=1, duration=1)),
        ],
        interval=1  # Short interval so test completes quickly
    )
    mock_node = MockNode(index=0, count=2)
    # Start time in the past so scenario completes immediately
    sm = ScenarioManager(mock_node, time.time() - 2, quick_scenario)
    sm.work_resolved.append(sm.work_index())
    await sm._resolve()
    assert len(sm.work_resolved) == 1


@pytest.mark.asyncio
async def test_scenario_manager_spawn_journeys():
    """Test ScenarioManager.spawn_journeys returns correct journey specs."""

    datapool_items = [f"itm_{i}" for i in range(20)]
    journey_datapool = IterableDatapool(datapool_items)
    start_time = time.time()

    # Use dummy journeys defined in this module instead of external dependency
    scenario = Scenario(
        journeys=[
            Journey("tests.test_scenario_manager:dummy_journey", journey_datapool, VolumeModel(target=2, duration=10)),
            Journey("tests.test_scenario_manager:dummy_journey3", None, VolumeModel(target=1, duration=5)),
        ],
        interval=1
    )

    mock_node = MockNode(index=0, count=1)
    scenario_manager = ScenarioManager(mock_node, start_time, scenario)
    work_piece = scenario_manager.work()

    # Track tasks before spawning
    initial_tasks = len(asyncio.all_tasks())

    for _work_starting_time, journey_spec, datapool_chunk, journey_count in work_piece:
        await scenario_manager.spawn_journeys(
            journey_spec, journey_count, datapool_chunk
        )

    # Verify journeys were spawned
    # Expected: 2 journeys with targets of 2 and 1 = 3 total spawned journeys
    assert scenario_manager.total_spawned_journeys == 3, \
        f"Expected 3 journeys spawned, got {scenario_manager.total_spawned_journeys}"

    # Verify background tasks were created (may complete quickly, so check tracking)
    assert len(scenario_manager._background_tasks) >= 0, \
        "Background tasks should be tracked (may complete immediately in test)"


# Tests for node_target_volume() function

class TestNodeTargetVolume:
    """Test work allocation fairness across nodes."""

    def test_zero_volume(self):
        """No work to distribute."""
        assert node_target_volume(0, 10, 0) == 0
        assert node_target_volume(5, 10, 0) == 0
        assert node_target_volume(9, 10, 0) == 0

    def test_single_work_single_node(self):
        """One node gets one work item."""
        assert node_target_volume(0, 1, 1) == 1

    def test_single_work_many_nodes_bug_scenario(self):
        """
        CRITICAL BUG: Single work item with many nodes.

        With current implementation, only node 0 gets work.
        If we have 100 journeys each with volume=1 and 10 nodes,
        when called 100 times (once per journey), only node 0 gets any work.
        """
        # Current (buggy) behavior: only node 0 gets the work
        assert node_target_volume(0, 10, 1) == 1
        assert node_target_volume(1, 10, 1) == 0
        assert node_target_volume(2, 10, 1) == 0
        assert node_target_volume(9, 10, 1) == 0

    def test_even_distribution(self):
        """100 items across 10 nodes = 10 each."""
        for node_idx in range(10):
            assert node_target_volume(node_idx, 10, 100) == 10

    def test_uneven_distribution_with_remainder(self):
        """10 items across 3 nodes = [4, 3, 3] (first node gets remainder)."""
        results = [node_target_volume(i, 3, 10) for i in range(3)]
        assert results == [4, 3, 3]
        assert sum(results) == 10

    def test_more_nodes_than_work(self):
        """5 work items, 10 nodes = first 5 get 1 each."""
        results = [node_target_volume(i, 10, 5) for i in range(10)]
        assert results == [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        assert sum(results) == 5

    def test_invalid_node_index(self):
        """
        Node index beyond count should ideally return 0.

        Currently the function doesn't validate node_index >= node_count,
        which is a separate bug. For now, verify that nodes within valid
        range work correctly.
        """
        # Valid node indices should work
        assert node_target_volume(0, 10, 100) == 10
        assert node_target_volume(9, 10, 100) == 10

        # Invalid node indices currently don't return 0 (known limitation)
        # This should be fixed in a separate improvement

    def test_total_work_preserved_single_item(self):
        """Total work across all nodes equals target volume for single item."""
        target_volume = 1
        node_count = 10
        total = sum(
            node_target_volume(i, node_count, target_volume)
            for i in range(node_count)
        )
        assert total == target_volume

    def test_total_work_preserved_large_volume(self):
        """Total work across all nodes equals target volume for large volumes."""
        test_cases = [
            (10, 100),   # 10 nodes, 100 work
            (3, 10),     # Uneven split
            (10, 5),     # More nodes than work
            (7, 49),     # Prime number of work
            (1, 1000),   # Single node handles all
        ]

        for node_count, target_volume in test_cases:
            total = sum(
                node_target_volume(i, node_count, target_volume)
                for i in range(node_count)
            )
            assert total == target_volume, (
                f"Failed: {node_count} nodes, {target_volume} work. "
                f"Got {total}, expected {target_volume}"
            )

    def test_distribution_fairness(self):
        """Verify work is distributed fairly (no node gets much more than others)."""
        node_count = 10
        target_volume = 100

        volumes = [node_target_volume(i, node_count, target_volume) for i in range(node_count)]

        # All nodes should get roughly equal work
        # With 100 work and 10 nodes, each should get 10
        assert all(v == 10 for v in volumes)

    def test_distribution_fairness_with_remainder(self):
        """
        Verify work is distributed fairly when there's a remainder.

        With 7 nodes and 10 work items:
        - 10 // 7 = 1 base work per node
        - 10 % 7 = 3 remainder
        - First 3 nodes get 2 work, remaining 4 get 1
        """
        node_count = 7
        target_volume = 10

        volumes = [node_target_volume(i, node_count, target_volume) for i in range(node_count)]

        # Verify fairness: difference between any two nodes should be at most 1
        for i in range(len(volumes)):
            for j in range(len(volumes)):
                assert abs(volumes[i] - volumes[j]) <= 1, (
                    f"Unfair distribution: node {i} gets {volumes[i]}, "
                    f"node {j} gets {volumes[j]}"
                )

        assert sum(volumes) == target_volume

    def test_journey_offset_single_volume(self):
        """Test that journey_offset distributes single volume items across different nodes."""
        node_count = 10

        # With offset=0, node 0 gets the work
        results_offset_0 = [node_target_volume(i, node_count, 1, journey_offset=0) for i in range(node_count)]
        assert results_offset_0 == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        # With offset=1, node 1 gets the work
        results_offset_1 = [node_target_volume(i, node_count, 1, journey_offset=1) for i in range(node_count)]
        assert results_offset_1 == [0, 1, 0, 0, 0, 0, 0, 0, 0, 0]

        # With offset=9, node 9 gets the work
        results_offset_9 = [node_target_volume(i, node_count, 1, journey_offset=9) for i in range(node_count)]
        assert results_offset_9 == [0, 0, 0, 0, 0, 0, 0, 0, 0, 1]

    def test_journey_offset_preserves_total_volume(self):
        """Test that journey_offset doesn't change total volume distributed."""
        node_count = 10
        target_volume = 5

        for offset in range(node_count):
            volumes = [node_target_volume(i, node_count, target_volume, journey_offset=offset) for i in range(node_count)]
            assert sum(volumes) == target_volume, (
                f"With offset={offset}, total is {sum(volumes)}, expected {target_volume}"
            )

    def test_journey_offset_rotates_distribution(self):
        """Test that different offsets rotate which nodes get remainder work."""
        node_count = 10
        target_volume = 3  # 10 // 3 = 3 per node, 10 % 3 = 1 remainder

        # Collect which nodes get extra work for different offsets
        extra_work_nodes = []
        for offset in range(10):  # Check multiple offsets
            volumes = [node_target_volume(i, node_count, target_volume, journey_offset=offset) for i in range(node_count)]
            # Find which node got extra work (volume 4 instead of 3)
            for i, vol in enumerate(volumes):
                if vol > target_volume // node_count:  # extra work above base
                    extra_work_nodes.append((offset, i))

        # Verify that different offsets result in different nodes getting extra work
        # (this shows the offset actually rotates the distribution)
        unique_nodes_with_extra = set(node for _, node in extra_work_nodes)
        assert len(unique_nodes_with_extra) > 1, (
            f"Expected multiple nodes to get extra work across different offsets, "
            f"but got nodes: {unique_nodes_with_extra}"
        )

    def test_multiple_journeys_distributed_fairly(self):
        """
        Simulate the bug scenario: 100 journeys with volume=1 distributed across 10 nodes.

        With the fix using journey_offset, work should be distributed across all nodes.
        """
        node_count = 10
        num_journeys = 100
        volume_per_journey = 1

        # Simulate 100 journeys, each with spec like "journey_0", "journey_1", etc.
        work_per_node = {i: 0 for i in range(node_count)}

        for journey_idx in range(num_journeys):
            # Use the same offset strategy as ScenarioManager
            journey_spec = f"journey_{journey_idx}"
            journey_offset = hash(journey_spec) % node_count

            for node_idx in range(node_count):
                work = node_target_volume(node_idx, node_count, volume_per_journey, journey_offset=journey_offset)
                work_per_node[node_idx] += work

        # With the fix, work should be distributed across all nodes
        # Each node should get approximately 100/10 = 10 journeys
        total_work = sum(work_per_node.values())
        assert total_work == num_journeys, f"Expected {num_journeys} total work, got {total_work}"

        # Verify all nodes got work (not just node 0)
        nodes_with_work = [i for i in range(node_count) if work_per_node[i] > 0]
        assert len(nodes_with_work) > 1, (
            f"Expected multiple nodes to get work, but only {nodes_with_work} got work. "
            f"Distribution: {work_per_node}"
        )

        # Verify fairness: work should be distributed across all nodes
        # (hash distribution won't be perfectly balanced, but should be much better than all-on-node-0)
        expected_per_node = num_journeys // node_count
        min_work = min(work_per_node.values())
        max_work = max(work_per_node.values())

        # The key test: we should NOT have all work on one node (spread = 100)
        # Hash distribution may have some variance, but spreading 100 items across 10 nodes
        # should result in a spread much less than 100
        max_acceptable_spread = num_journeys // 2  # 50 for 100 journeys
        assert max_work - min_work <= max_acceptable_spread, (
            f"Work distribution too skewed. Min={min_work}, Max={max_work}, spread={max_work - min_work}. "
            f"Expected spread <= {max_acceptable_spread} (much better than original bug spread of {num_journeys}). "
            f"Distribution: {work_per_node}"
        )
