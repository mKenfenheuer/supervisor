"""Test docker stats."""

import pytest

from supervisor.dbus.agent.gpu import GPUContainerUsage
from supervisor.docker.stats import DockerStats

from tests.common import load_json_fixture


@pytest.mark.parametrize(
    "stats_mock",
    ["container_stats", "container_stats_cgroupv1", "container_stats_cgroupv2"],
)
def test_cpu_percentage(stats_mock: str):
    """Test CPU percentage."""
    stats_fixture = load_json_fixture(f"{stats_mock}.json")
    stats = DockerStats(stats_fixture)

    stats._calc_cpu_percent(stats_fixture)  # pylint: disable=protected-access
    assert stats.cpu_percent == 90.0

    stats_fixture["cpu_stats"]["cpu_usage"]["total_usage"] = 0
    stats_fixture["precpu_stats"]["cpu_usage"]["total_usage"] = 0
    stats_fixture["cpu_stats"]["system_cpu_usage"] = 0
    stats_fixture["precpu_stats"]["system_cpu_usage"] = 0
    stats._calc_cpu_percent(stats_fixture)  # pylint: disable=protected-access
    assert stats.cpu_percent == 0.0


@pytest.mark.parametrize(
    "stats_mock",
    ["container_stats", "container_stats_cgroupv1", "container_stats_cgroupv2"],
)
async def test_memory_usage(stats_mock: str):
    """Test memory usage calculation."""
    stats_fixture = load_json_fixture(f"{stats_mock}.json")
    stats = DockerStats(stats_fixture)

    assert stats.memory_limit == 4000000000
    assert stats.memory_usage == 59700000
    assert stats.memory_percent == 1.49


def test_gpu_usage():
    """Test GPU usage summed up over the GPUs of a container."""
    stats = DockerStats(load_json_fixture("container_stats.json"))
    assert stats.gpu_memory_usage is None
    assert stats.gpu_memory_limit is None
    assert stats.gpu_memory_percent is None
    assert stats.gpu_percent is None

    stats.set_gpu_usage(
        [
            GPUContainerUsage("c", "0000:01:00.0", 1000, 30.0),
            GPUContainerUsage("c", "0000:02:00.0", 3000, None),
        ],
        {"0000:01:00.0": 4000, "0000:02:00.0": 4000},
    )
    assert stats.gpu_memory_usage == 4000
    assert stats.gpu_memory_limit == 8000
    assert stats.gpu_memory_percent == 50.0
    assert stats.gpu_percent == 30.0


def test_gpu_usage_unknown_values():
    """Test GPU usage without memory of the GPU and without utilization."""
    stats = DockerStats(load_json_fixture("container_stats.json"))
    stats.set_gpu_usage(
        [GPUContainerUsage("c", "0000:00:02.0", 1000, None)],
        {"0000:00:02.0": None},
    )
    assert stats.gpu_memory_usage == 1000
    assert stats.gpu_memory_limit is None
    assert stats.gpu_memory_percent is None
    assert stats.gpu_percent is None
