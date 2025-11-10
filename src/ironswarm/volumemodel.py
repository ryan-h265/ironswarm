from math import ceil


class JourneyComplete(Exception):
    pass


class VolumeModel:
    """
    A base class for volume models that defines the target volume and duration.
    """

    def __init__(self, target: int = 1, duration: int | None = None, interval: int = 1) -> None:
        self.target = target
        self.duration = duration
        self._interval = interval

    def __repr__(self) -> str:
        return f"VolumeModel. Duration: {self.duration} Target: {self.target}"

    @property
    def interval(self) -> int:
        return self._interval

    def __call__(self, time_delta: int, *args, **kwds) -> int:
        if self.duration and time_delta >= self.duration:
            msg = f"Duration of {self.duration!r} achieved"
            raise JourneyComplete(msg)

        return self.target

    def cumulative_volume(self, start_time: int, end_time: int) -> int:
        """
        Calculate cumulative volume from start_time to end_time (inclusive).

        For constant volume models, this is O(1): target * time_range
        Subclasses can override for dynamic volume calculations.

        Args:
            start_time: Starting time (inclusive)
            end_time: Ending time (inclusive)

        Returns:
            Total volume over the time range
        """
        if end_time < start_time:
            return 0

        time_range = end_time - start_time + 1
        return self.target * time_range


class DynamicVolumeModel(VolumeModel):
    """
    A volume model that supports dynamic changes to the target volume over time.

    """
    def __init__(
        self,
        target: int = 1,
        duration: int | None = None,
        interval: int = 1,
        ramp_up: int | None = None,
        ramp_down: int | None = None,
    ) -> None:
        super().__init__(target, duration, interval)
        self.ramp_up = ramp_up or 0
        self.ramp_down = ramp_down

        if self.duration is None and ramp_down is not None:
            raise ValueError("Ramp down requires a defined duration")

    def __repr__(self) -> str:
        return f"VolumeModel. Duration: {self.duration} Target: {self.target} RampUp: {self.ramp_up} RampDown: {self.ramp_down}"

    def _ramp_up(self, time_delta: int) -> int:
        return ceil(self.target * (time_delta / self.ramp_up))

    def _ramp_down(self, time_delta: int) -> int:
        remaining_time = self.duration - time_delta  # type: ignore[operator]
        ramp_down_time = self.duration - self.ramp_down  # type: ignore[operator]

        return ceil(self.target * (remaining_time / ramp_down_time))

    def __call__(self, time_delta: int, *args, **kwds) -> int:
        if self.duration and time_delta >= self.duration:
            msg = f"Duration of {self.duration!r} achieved"
            raise JourneyComplete(msg)

        if self.ramp_up and time_delta <= self.ramp_up:
            return self._ramp_up(time_delta)

        if self.ramp_down and time_delta >= self.ramp_down:
            return self._ramp_down(time_delta)

        return self.target

    def cumulative_volume(self, start_time: int, end_time: int) -> int:
        """
        Calculate cumulative volume for dynamic ramp models.

        This is more complex than constant volume due to ramps,
        but still more efficient than calling __call__ for each time step.

        Args:
            start_time: Starting time (inclusive)
            end_time: Ending time (inclusive)

        Returns:
            Total volume over the time range
        """
        if end_time < start_time:
            return 0

        total = 0
        for t in range(start_time, end_time + 1):
            try:
                total += self(t)
            except JourneyComplete:
                break

        return total
