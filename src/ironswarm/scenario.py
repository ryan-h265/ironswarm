from collections import namedtuple
from dataclasses import dataclass

Journey = namedtuple("Journey", ["spec", "datapool", "volumemodel"])


@dataclass
class Scenario:
    journeys: list[Journey]
    interval: int = 30
    delay: int = 30
    journey_separation: float = 1.0
