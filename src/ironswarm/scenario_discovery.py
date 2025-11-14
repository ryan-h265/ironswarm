"""Scenario discovery and validation utilities for IronSwarm.

This module provides functions for:
- Discovering scenario files in a directory
- Validating scenario files (syntax, structure, import)
- Extracting scenario metadata
- Converting file paths to module specifications
"""

import ast
import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from ironswarm.scenario import Scenario
from ironswarm.volumemodel import VolumeModel, DynamicVolumeModel

log = logging.getLogger(__name__)


class ScenarioValidationError(Exception):
    """Raised when scenario validation fails."""
    pass


def discover_scenarios(directory: Path) -> list[dict[str, Any]]:
    """Discover all valid scenario files in a directory.

    Args:
        directory: Path to directory containing scenario files.

    Returns:
        List of dictionaries containing scenario information:
        {
            'file_path': Path,
            'module_spec': str,
            'name': str,
            'metadata': dict,
            'valid': bool,
            'error': str | None
        }
    """
    if not directory.exists():
        log.warning(f"Scenarios directory does not exist: {directory}")
        return []

    if not directory.is_dir():
        log.error(f"Scenarios path is not a directory: {directory}")
        return []

    scenarios = []

    for py_file in directory.glob("*.py"):
        if py_file.name.startswith("_"):
            # Skip private modules like __init__.py
            continue

        scenario_info = {
            'file_path': str(py_file),
            'name': py_file.stem,
            'valid': False,
            'error': None,
            'module_spec': None,
            'metadata': None,
        }

        try:
            # Validate the scenario file
            scenario_obj = validate_scenario_file(py_file)

            # Convert to module spec
            module_spec = file_path_to_module_spec(py_file, directory.parent)

            # Extract metadata
            metadata = get_scenario_metadata(scenario_obj)

            scenario_info.update({
                'valid': True,
                'module_spec': module_spec,
                'metadata': metadata,
            })

        except ScenarioValidationError as e:
            scenario_info['error'] = str(e)
            log.debug(f"Invalid scenario file {py_file}: {e}")
        except Exception as e:
            scenario_info['error'] = f"Unexpected error: {str(e)}"
            log.error(f"Error processing scenario file {py_file}: {e}", exc_info=True)

        scenarios.append(scenario_info)

    return scenarios


def validate_scenario_file(file_path: Path) -> Scenario:
    """Validate a scenario file at three levels: syntax, structure, and import.

    Args:
        file_path: Path to the Python file to validate.

    Returns:
        The validated Scenario object.

    Raises:
        ScenarioValidationError: If validation fails at any level.
    """
    # Level 1: Syntax validation
    try:
        with open(file_path, 'r') as f:
            source_code = f.read()
        ast.parse(source_code)
    except SyntaxError as e:
        raise ScenarioValidationError(f"Syntax error: {e}")
    except Exception as e:
        raise ScenarioValidationError(f"Failed to read file: {e}")

    # Level 2: Structure validation - check for 'scenario' variable
    try:
        tree = ast.parse(source_code)
        has_scenario_var = False

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'scenario':
                        has_scenario_var = True
                        break

        if not has_scenario_var:
            raise ScenarioValidationError(
                "File must contain a 'scenario' variable assignment"
            )
    except ScenarioValidationError:
        raise
    except Exception as e:
        raise ScenarioValidationError(f"Structure validation failed: {e}")

    # Level 3: Import attempt validation
    try:
        # Load the module dynamically
        spec = importlib.util.spec_from_file_location(
            f"scenario_{file_path.stem}",
            file_path
        )
        if spec is None or spec.loader is None:
            raise ScenarioValidationError("Failed to create module spec")

        module = importlib.util.module_from_spec(spec)

        # Temporarily add to sys.modules to allow relative imports
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            # Clean up sys.modules
            sys.modules.pop(spec.name, None)

        # Check if 'scenario' attribute exists
        if not hasattr(module, 'scenario'):
            raise ScenarioValidationError(
                "Module does not have a 'scenario' attribute"
            )

        scenario_obj = module.scenario

        # Validate it's a Scenario instance
        if not isinstance(scenario_obj, Scenario):
            raise ScenarioValidationError(
                f"'scenario' must be a Scenario instance, got {type(scenario_obj)}"
            )

        # Validate journeys
        if not scenario_obj.journeys:
            raise ScenarioValidationError("Scenario must have at least one journey")

        for idx, journey in enumerate(scenario_obj.journeys):
            if not journey.spec:
                raise ScenarioValidationError(
                    f"Journey {idx} must have a spec"
                )
            if not isinstance(journey.volumemodel, (VolumeModel, DynamicVolumeModel)):
                raise ScenarioValidationError(
                    f"Journey {idx} must have a valid VolumeModel"
                )

        return scenario_obj

    except ScenarioValidationError:
        raise
    except ImportError as e:
        raise ScenarioValidationError(f"Import failed: {e}")
    except Exception as e:
        raise ScenarioValidationError(f"Import validation failed: {e}")


def get_scenario_metadata(scenario: Scenario) -> dict[str, Any]:
    """Extract metadata from a Scenario object.

    Args:
        scenario: The Scenario object to extract metadata from.

    Returns:
        Dictionary containing scenario metadata including journeys,
        interval, delay, and journey details.
    """
    journeys_metadata = []

    for journey in scenario.journeys:
        journey_info = {
            'spec': journey.spec,
            'datapool': journey.datapool,
        }

        # Extract volume model information
        vm = journey.volumemodel
        if isinstance(vm, VolumeModel):
            journey_info['volumemodel'] = {
                'type': 'VolumeModel',
                'target': vm.target,
                'duration': vm.duration,
            }
        elif isinstance(vm, DynamicVolumeModel):
            journey_info['volumemodel'] = {
                'type': 'DynamicVolumeModel',
                'schedule': vm.schedule,
            }
        else:
            journey_info['volumemodel'] = {
                'type': 'Unknown',
                'value': str(vm),
            }

        journeys_metadata.append(journey_info)

    return {
        'interval': scenario.interval,
        'delay': scenario.delay,
        'journey_separation': scenario.journey_separation,
        'journeys': journeys_metadata,
        'journey_count': len(scenario.journeys),
    }


def file_path_to_module_spec(file_path: Path, base_dir: Path) -> str:
    """Convert a file path to a Python module specification.

    Args:
        file_path: Path to the Python file.
        base_dir: Base directory to calculate relative path from.

    Returns:
        Module specification in format 'module.path:attribute'.
        Example: 'scenarios.http_scenario:scenario'

    Raises:
        ValueError: If file_path is not relative to base_dir.
    """
    try:
        # Get relative path from base_dir
        relative_path = file_path.relative_to(base_dir)
    except ValueError:
        raise ValueError(
            f"File path {file_path} is not relative to base directory {base_dir}"
        )

    # Convert path to module notation
    # e.g., scenarios/http_scenario.py -> scenarios.http_scenario
    module_parts = list(relative_path.parts[:-1])  # All parts except filename
    module_parts.append(relative_path.stem)  # Add filename without .py extension

    module_path = '.'.join(module_parts)

    # Append :scenario to create full spec
    return f"{module_path}:scenario"
