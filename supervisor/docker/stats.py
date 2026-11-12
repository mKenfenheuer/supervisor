"""Calc and represent docker stats data."""

from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..dbus.agent.gpu import GPUContainerUsage


class DockerStats:
    """Hold stats data from container inside."""

    def __init__(self, stats):
        """Initialize Docker stats."""
        self._cpu_percent: float | None = None
        self._cpu_usage = 0
        self._cpu_system_usage = 0
        self._online_cpus = 0
        self._network_rx = 0
        self._network_tx = 0
        self._blk_read = 0
        self._blk_write = 0
        self._container_id: str | None = stats.get("id")
        self._gpu_memory_usage: int | None = None
        self._gpu_memory_limit: int | None = None
        self._gpu_percent: float | None = None

        try:
            # cgroupv1 & Docker > 19.03
            if "total_inactive_file" in stats["memory_stats"]["stats"]:
                cache = stats["memory_stats"]["stats"]["total_inactive_file"]

            # Docker <= 19.03
            elif "cache" in stats["memory_stats"]["stats"]:
                cache = stats["memory_stats"]["stats"]["cache"]

            # cgroupv2
            else:
                cache = stats["memory_stats"]["stats"]["inactive_file"]

            self._memory_usage = stats["memory_stats"]["usage"] - cache
            self._memory_limit = stats["memory_stats"]["limit"]
        except KeyError:
            self._memory_usage = 0
            self._memory_limit = 0

        # Calculate percent usage
        if self._memory_limit != 0:
            self._memory_percent = self._memory_usage / self._memory_limit * 100.0
        else:
            self._memory_percent = 0

        with suppress(KeyError):
            self._calc_cpu_usage(stats)

        with suppress(KeyError):
            self._calc_cpu_percent(stats)

        with suppress(KeyError):
            self._calc_network(stats["networks"])

        with suppress(KeyError, TypeError):
            self._calc_block_io(stats["blkio_stats"])

    def set_gpu_usage(
        self, usage: list[GPUContainerUsage], memory_total: dict[str, int | None]
    ) -> None:
        """Add the GPU usage of the container, summed up over its GPUs.

        memory_total holds the memory of each GPU by address.
        """
        if not usage:
            return
        memory = [u.memory_used for u in usage if u.memory_used is not None]
        if memory:
            self._gpu_memory_usage = sum(memory)
            totals = [memory_total.get(u.address) for u in usage]
            if all(total is not None for total in totals):
                self._gpu_memory_limit = sum(totals)  # type: ignore[arg-type]
        utilization = [u.utilization for u in usage if u.utilization is not None]
        if utilization:
            self._gpu_percent = max(utilization)

    def _calc_cpu_usage(self, stats):
        """Extract the raw, cumulative CPU counters reported by Docker.

        These are absolute totals since the container started (not a
        windowed/calculated rate) and are always available, even for a
        one-shot sample that has no previous data point to compare against.
        """
        self._cpu_usage = stats["cpu_stats"]["cpu_usage"]["total_usage"]
        self._cpu_system_usage = stats["cpu_stats"]["system_cpu_usage"]
        self._online_cpus = stats["cpu_stats"]["online_cpus"]

    def _calc_cpu_percent(self, stats):
        """Calculate CPU percent from the delta between two samples.

        Requires ``precpu_stats`` from a previous sample, which is only
        present when Docker was given a window to measure over. Left as
        ``None`` when that data isn't available (e.g. a one-shot sample).
        """
        cpu_delta = (
            stats["cpu_stats"]["cpu_usage"]["total_usage"]
            - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        )
        system_delta = (
            stats["cpu_stats"]["system_cpu_usage"]
            - stats["precpu_stats"]["system_cpu_usage"]
        )

        if system_delta > 0.0 and cpu_delta > 0.0:
            self._cpu_percent = (cpu_delta / system_delta) * 100.0
        else:
            self._cpu_percent = 0.0

    def _calc_network(self, networks):
        """Calculate Network IO stats."""
        for _, stats in networks.items():
            self._network_rx += stats["rx_bytes"]
            self._network_tx += stats["tx_bytes"]

    def _calc_block_io(self, blkio):
        """Calculate block IO stats."""
        for stats in blkio["io_service_bytes_recursive"]:
            if stats["op"] == "Read":
                self._blk_read += stats["value"]
            elif stats["op"] == "Write":
                self._blk_write += stats["value"]

    @property
    def cpu_percent(self):
        """Return CPU percent, or None if no measurement window was available."""
        return None if self._cpu_percent is None else round(self._cpu_percent, 2)

    @property
    def cpu_usage(self):
        """Return total CPU time (in nanoseconds) used by the container so far."""
        return self._cpu_usage

    @property
    def cpu_system_usage(self):
        """Return total CPU time (in nanoseconds) used by the system at sample time."""
        return self._cpu_system_usage

    @property
    def online_cpus(self):
        """Return the number of CPUs available to the container."""
        return self._online_cpus

    @property
    def memory_usage(self):
        """Return memory usage."""
        return self._memory_usage

    @property
    def memory_limit(self):
        """Return memory limit."""
        return self._memory_limit

    @property
    def memory_percent(self):
        """Return memory usage in percent."""
        return round(self._memory_percent, 2)

    @property
    def network_rx(self):
        """Return network rx stats."""
        return self._network_rx

    @property
    def network_tx(self):
        """Return network rx stats."""
        return self._network_tx

    @property
    def blk_read(self):
        """Return block IO read stats."""
        return self._blk_read

    @property
    def blk_write(self):
        """Return block IO write stats."""
        return self._blk_write

    @property
    def container_id(self) -> str | None:
        """Return the ID of the container."""
        return self._container_id

    @property
    def gpu_memory_usage(self) -> int | None:
        """Return GPU memory usage in bytes, None if the container uses no GPU."""
        return self._gpu_memory_usage

    @property
    def gpu_memory_limit(self) -> int | None:
        """Return the memory of the GPUs the container uses in bytes."""
        return self._gpu_memory_limit

    @property
    def gpu_memory_percent(self) -> float | None:
        """Return GPU memory usage in percent of the memory of its GPUs."""
        if not self._gpu_memory_limit or self._gpu_memory_usage is None:
            return None
        return round(self._gpu_memory_usage / self._gpu_memory_limit * 100.0, 2)

    @property
    def gpu_percent(self) -> float | None:
        """Return the utilization of the busiest GPU the container uses."""
        return None if self._gpu_percent is None else round(self._gpu_percent, 2)
