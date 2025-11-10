import pytest

from ironswarm.volumemodel import DynamicVolumeModel, JourneyComplete, VolumeModel


def test_volumemodel_initialization():
    vm = VolumeModel(target=5, duration=10)
    assert vm.duration == 10
    assert vm.target == 5
    assert repr(vm) == "VolumeModel. Duration: 10 Target: 5"


def test_volumemodel_call_within_duration():
    vm = VolumeModel(target=5, duration=10)
    result = vm(5)
    assert result == 5


def test_volumemodel_call_exceeding_duration():
    vm = VolumeModel(target=5, duration=10)
    with pytest.raises(JourneyComplete, match="Duration of 10 achieved"):
        vm(10)


def test_volumemodel_call_no_duration():
    vm = VolumeModel(target=3, duration=None)
    result = vm(15)
    assert result == 3


def test_dynamic_volumemodel_initialization():
    dvm = DynamicVolumeModel(target=5, duration=10, ramp_up=2, ramp_down=8)
    assert dvm.target == 5
    assert dvm.duration == 10
    assert dvm.ramp_up == 2
    assert dvm.ramp_down == 8
    assert dvm.interval == 1
    assert repr(dvm) == "VolumeModel. Duration: 10 Target: 5 RampUp: 2 RampDown: 8"


def test_dynamic_volumemodel_call():
    dvm = DynamicVolumeModel(target=100, duration=60, ramp_up=5, ramp_down=55)

    # Full duration, should hit target
    result = dvm(10)
    assert result == 100


def test_dynamic_volumemodel_call_within_ramp_up():
    dvm = DynamicVolumeModel(target=100, duration=300, ramp_up=60)

    # Quarter way through ramp-up
    result = dvm(15)
    assert result == 25


def test_dynamic_volumemodel_call_within_ramp_down():
    dvm = DynamicVolumeModel(target=100, duration=20, ramp_down=10)
    result = dvm(15)
    assert result == 50  # Half way through ramp-down


def test_dynamic_volumemodel_call_exceeding_ramp_up():
    dvm = DynamicVolumeModel(target=100, duration=20, ramp_up=10)
    result = dvm(10)
    assert result == 100  # Ramp-up complete, should hit target


def test_dynamic_volumemodel_ramp_down():
    dvm = DynamicVolumeModel(target=100, duration=20, ramp_down=15)
    result = dvm(18)
    assert result == 40  # Near the end of ramp-down


def test_dynamic_volumemodel_call_exceeding_duration():
    vm = DynamicVolumeModel(target=5, duration=10, ramp_up=2, ramp_down=8)
    with pytest.raises(JourneyComplete, match="Duration of 10 achieved"):
        vm(10)


def test_dynamic_volumemodel_ramp_down_has_duration():
    with pytest.raises(ValueError, match="Ramp down requires a defined duration"):
        _vm = DynamicVolumeModel(target=5, ramp_up=2, ramp_down=8)
