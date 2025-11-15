from __future__ import annotations

import asyncio
import importlib
import logging
import time
from collections import namedtuple
from collections.abc import Iterator
from typing import Any

from ironswarm.context import Context
from ironswarm.metrics.events import record_journey_failure, record_journey_success
from ironswarm.scenario import Journey, Scenario
from ironswarm.types import NodeType
from ironswarm.volumemodel import JourneyComplete

log = logging.getLogger(__name__)


Work = namedtuple("Work", ["start_time", "journey_spec", "data", "subint_volumes"])

def spec_import(spec: str) -> Any:
    """Import a journey function from a module spec.

    Args:
        spec: Module specification in format 'module:attribute'.

    Returns:
        The imported journey function/class.

    Raises:
        ValueError: If spec format is invalid.
    """
    if ":" not in spec:
        raise ValueError("Invalid spec format. Expected 'module:attribute'.")
    module, attr = spec.split(":", 1)
    return getattr(importlib.import_module(module), attr)


class ScenarioManager:
    def __init__(
        self,
        node: NodeType,
        start_time: float,
        scenario: Scenario,
    ) -> None:
        self.node: NodeType = node
        self.start_time: float = start_time
        self.scenario: Scenario = scenario

        self.work_resolved: list[int] = []
        self.journeys_complete: dict[Journey, int] = {}

        self.total_spawned_journeys: int = 0

        self.running: bool = False

        # Track background tasks for graceful shutdown
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def work_index(self) -> int:
        return int(self.elapsed // self.scenario.interval)

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time

    async def resolve(self) -> None:
        """Main loop to resolve work intervals."""
        self.running = True
        while self.running:
            # calculate time until next work interval
            time_until_next_interval = self.scenario.interval - self.elapsed % self.scenario.interval
            log.debug(f"Time until next work interval: {time_until_next_interval}")
            await asyncio.sleep(time_until_next_interval)

            await self._resolve()

    async def _resolve(self) -> None:
        """Process a single work interval."""
        if self.work_index() in self.work_resolved:
            # Already processed this work interval
            # Check if scenario is complete to exit early instead of sleeping
            if not self.running:
                return  # Scenario complete, exit immediately
            await asyncio.sleep(self.scenario.journey_separation)
            return

        self.work_resolved.append(self.work_index())
        work_interval = self.work()
        for work in work_interval:
            task = asyncio.create_task(
                self.spawn_journeys(work.journey_spec, work.subint_volumes, work.data)
            )
            self._background_tasks.add(task)
            # Remove task from set when done to avoid memory leak
            task.add_done_callback(self._background_tasks.discard)

    async def spawn_journeys(
        self,
        journey_spec: str,
        journey_spawns: list[int],
        datapool_chunk: Iterator[Any] | None = None,
    ) -> None:
        """Spawn journey instances with proper Context lifecycle management.

        Each journey gets its own Context for:
        - Unique trace/span IDs
        - Isolated HTTP sessions
        - Proper resource cleanup

        Args:
            journey_spec: Module spec for journey function.
            journey_spawns: List of volumes per sub-interval.
            datapool_chunk: Optional iterator of datapool items.
        """
        journey_object = spec_import(journey_spec)

        for interval_idx in range(int(self.scenario.interval / self.scenario.journey_separation)):
            try:
                sub_interval_volume = journey_spawns[interval_idx]
            except IndexError:
                return

            for _ in range(sub_interval_volume):
                # Create fresh Context for each journey execution
                # Provides unique trace ID and isolated resources
                context = Context(
                    metadata={
                        "scenario": self.scenario.__class__.__name__,
                        "journey_spec": journey_spec,
                        "node": self.node.identity,
                    }
                )

                if datapool_chunk:
                    try:
                        datapool_item = next(datapool_chunk)
                        task = asyncio.create_task(self._run_journey_with_context(
                            journey_object, context, datapool_item
                        ))
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)
                    except StopIteration:
                        log.warning("Datapool exhausted. No more items available.")
                        break
                else:
                    task = asyncio.create_task(self._run_journey_with_context(
                        journey_object, context
                    ))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

                self.total_spawned_journeys += 1

            await asyncio.sleep(self.scenario.journey_separation)

    async def _run_journey_with_context(
        self, journey_func: Any, context: Context, *args: Any
    ) -> Any:
        """Execute journey with automatic Context cleanup.

        Ensures Context.close() is called even if journey raises exception.

        Args:
            journey_func: Journey function to execute.
            context: Context instance for this journey.
            *args: Additional arguments to pass to journey.

        Returns:
            Return value from journey function.
        """
        start = time.perf_counter()
        try:
            async with context:
                result = await journey_func(context, *args)
            duration = time.perf_counter() - start
            record_journey_success(context, duration)
            return result
        except Exception as e:
            duration = time.perf_counter() - start
            record_journey_failure(context, duration, error=e)
            log.error(f"Journey {journey_func.__name__} failed: {e}", exc_info=True)

    async def cancel_tasks(self) -> None:
        """Cancel all background tasks gracefully."""
        if not self._background_tasks:
            return

        log.info(f"Cancelling {len(self._background_tasks)} background tasks...")
        for task in self._background_tasks:
            task.cancel()

        # Wait for all tasks to complete cancellation
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        log.info("All background tasks cancelled.")

    def work(self, work_index: int | None = None) -> list[Work]:
        work_index = work_index or self.work_index()
        work_start_time = work_index * self.scenario.interval
        work_interval: list[Work] = []

        scenario_complete = True
        for journey in self.scenario.journeys:
            completed_index = self.journeys_complete.get(journey)
            if journey in self.journeys_complete and completed_index is not None and completed_index < work_index:
                continue
            scenario_complete = False

            # Create a fresh list for THIS journey's subinterval volumes
            # This prevents sharing state across multiple journeys
            subinterval_volumes: list[int] = []

            # Use journey spec hash to deterministically distribute journeys across nodes
            # This prevents all journeys with small volumes from going to node 0
            journey_offset = hash(journey.spec) % self.node.count

            node_total_journeys: dict[int, int] = {}
            for i in range(self.scenario.interval):
                try:
                    journey_volume_i = journey.volumemodel(work_start_time + i)

                    for node_index in range(self.node.count):
                        node_volume = node_target_volume(
                            node_index, self.node.count, journey_volume_i, journey_offset=journey_offset
                        )
                        node_total_journeys[node_index] = node_total_journeys.get(node_index, 0) + node_volume
                        if node_index == self.node.index:
                            subinterval_volumes.append(node_volume)

                except JourneyComplete:
                    log.warning(f"Journey will be completed, after next interval: {journey.spec=}, removing from scenario")
                    self.journeys_complete[journey] = work_index
                    break

            total_journey_calls = sum(node_total_journeys.values())

            if total_journey_calls == 0:
                continue

            datapool_chunk = None
            if journey.datapool and self.node.index is not None:
                # if work_index > 0 and journey.datapool.index == 0
                # we can assume we've joined the scenario late
                # and we need to calculate the journey.datapool.index
                # using the journey.volumemodel
                if work_index > 0 and journey.datapool.index == 0:
                    # Use O(1) cumulative volume calculation instead of O(n) loop
                    journey.datapool.index = journey.volumemodel.cumulative_volume(
                        0, work_start_time - 1
                    )

                node_offset = sum(
                    node_total for idx, node_total in node_total_journeys.items() if idx < self.node.index
                )
                checkout_start = journey.datapool.index + node_offset
                checkout_stop = checkout_start + node_total_journeys[self.node.index]

                # Check if datapool is exhausted before attempting checkout
                if checkout_start > len(journey.datapool):
                    # Datapool exhausted, return empty iterator
                    datapool_chunk = iter([])
                else:
                    datapool_chunk = journey.datapool.checkout(checkout_start, checkout_stop)

                journey.datapool.index += total_journey_calls

            work_interval.append(
                Work(work_start_time, journey.spec, datapool_chunk, subinterval_volumes)
            )

        if scenario_complete:
            log.warning("Scenario complete, no more work to be done")
            self.running = False

        return work_interval


def node_target_volume(
    node_index: int, node_count: int, target_volume: int, journey_offset: int = 0
) -> int:
    """
    Distribute target_volume work items fairly across node_count nodes.

    Args:
        node_index: Zero-based index of this node (0 to node_count-1)
        node_count: Total number of nodes in the cluster
        target_volume: Total work items to distribute this interval
        journey_offset: Optional offset for deterministic distribution across multiple calls
                       (used to prevent all journeys with volume=1 going to node 0)

    Returns:
        Number of work items this node should handle

    Examples:
        >>> node_target_volume(0, 10, 100)  # Node 0 of 10, 100 items
        10
        >>> node_target_volume(9, 10, 100)  # Node 9 of 10, 100 items
        10
        >>> node_target_volume(0, 10, 1)    # Node 0 of 10, 1 item (no offset)
        1
        >>> node_target_volume(1, 10, 1)    # Node 1 of 10, 1 item (no offset)
        0
        >>> node_target_volume(0, 10, 1, journey_offset=1)  # With offset, rotates
        0
        >>> node_target_volume(1, 10, 1, journey_offset=1)  # With offset, node 1 gets it
        1
    """
    # No work to distribute
    if target_volume == 0:
        return 0

    # Validate node index
    if node_index >= node_count:
        return 0

    # Standard case: distribute work evenly with remainder handling
    base_volume = target_volume // node_count
    remainder = target_volume % node_count

    # Apply journey_offset to rotate which nodes get the remainder work
    # This ensures that different journeys (via different offsets) get distributed
    # across different nodes instead of all going to node 0
    remainder_start = journey_offset % node_count
    remainder_end = (remainder_start + remainder) % node_count

    # Check if this node falls within the remainder range (accounting for wraparound)
    if remainder > 0:
        if remainder_end > remainder_start:
            # Normal case: remainder goes to nodes [remainder_start, remainder_end)
            node_gets_remainder = remainder_start <= node_index < remainder_end
        else:
            # Wraparound case: remainder goes to nodes [remainder_start, n) + [0, remainder_end)
            node_gets_remainder = node_index >= remainder_start or node_index < remainder_end

        if node_gets_remainder:
            return base_volume + 1

    return base_volume
