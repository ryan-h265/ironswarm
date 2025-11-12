import asyncio
import logging
from typing import Any

from ironswarm.scenario import Scenario
from ironswarm.scenario_manager import ScenarioManager, spec_import
from ironswarm.types import NodeType

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self.scenarios: list[str] = []
        self.scenario_managers: list[ScenarioManager] = []
        self.running: bool = True
        # Track scenario tasks for graceful shutdown
        self._scenario_tasks: dict[str, asyncio.Task] = {}

    def scenario_resolve_task(self, node: NodeType, scenario: Scenario, start_time: float) -> ScenarioManager:
        """Create and register a scenario manager for a given scenario."""
        scenario_manager = ScenarioManager(
            node, start_time, scenario
        )
        self.scenario_managers.append(scenario_manager)
        return scenario_manager

    async def run(self, node: NodeType) -> None:
        while self.running:
            await asyncio.sleep(1)

            if not node.state["scenarios"].values():
                continue

            for scenario_spec, info in node.state["scenarios"].values():
                if scenario_spec in self.scenarios:
                    continue

                scenario_obj: Any = spec_import(scenario_spec)
                scenario: Scenario = scenario_obj  # Type assertion - we expect it to be a Scenario
                start_time = info["init_time"] + scenario.delay

                scenario_manager = self.scenario_resolve_task(node, scenario, start_time)
                task = asyncio.create_task(scenario_manager.resolve())
                self._scenario_tasks[scenario_spec] = task
                self.scenarios.append(scenario_spec)
                log.info(f"Started new scenario: {scenario_spec}")

            # Clean up completed scenarios
            await self._cleanup_completed_scenarios()

        log.info("Scheduler shutting down...")

    async def _cleanup_completed_scenarios(self) -> None:
        """Remove completed scenario managers and their tasks."""
        completed_specs = []
        for spec, task in self._scenario_tasks.items():
            if task.done():
                completed_specs.append(spec)

        for spec in completed_specs:
            self._scenario_tasks.pop(spec, None)
            if spec in self.scenarios:
                self.scenarios.remove(spec)
                log.info(f"Removed completed scenario: {spec}")

            # Also remove from scenario_managers list
            self.scenario_managers = [
                sm for sm in self.scenario_managers
                if sm.running
            ]

    async def shutdown(self) -> None:
        """Gracefully shutdown all running scenarios."""
        log.info("Shutting down scheduler...")
        self.running = False

        # Stop all scenario managers
        for manager in self.scenario_managers:
            manager.running = False
            await manager.cancel_tasks()

        # Cancel all scenario tasks
        for spec, task in self._scenario_tasks.items():
            log.info(f"Cancelling scenario: {spec}")
            task.cancel()

        # Wait for all tasks to complete
        if self._scenario_tasks:
            await asyncio.gather(*self._scenario_tasks.values(), return_exceptions=True)

        self._scenario_tasks.clear()
        self.scenarios.clear()
        self.scenario_managers.clear()
        log.info("Scheduler shutdown complete.")
