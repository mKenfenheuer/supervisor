"""GPU object for OS Agent."""

from dataclasses import dataclass
from typing import Any

from ..const import DBUS_NAME_HAOS, DBUS_OBJECT_HAOS_GPU
from ..interface import DBusInterface
from ..utils import dbus_connected


@dataclass(slots=True, frozen=True)
class GPUDevice:
    """GPU of the host with current statistics, None if the driver lacks them."""

    address: str
    vendor: str
    name: str
    driver: str
    driver_version: str
    utilization: float | None
    memory_used: int | None
    memory_total: int | None
    temperature: float | None
    power: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GPUDevice:
        """Create GPU device from D-Bus dictionary."""
        return cls(
            address=data.get("Address", ""),
            vendor=data.get("Vendor", ""),
            name=data.get("Name", ""),
            driver=data.get("Driver", ""),
            driver_version=data.get("DriverVersion", ""),
            utilization=data.get("Utilization"),
            memory_used=data.get("MemoryUsed"),
            memory_total=data.get("MemoryTotal"),
            temperature=data.get("Temperature"),
            power=data.get("Power"),
        )


@dataclass(slots=True, frozen=True)
class GPUContainerUsage:
    """GPU usage of the processes of a container, None if the driver lacks it."""

    container: str
    address: str
    memory_used: int | None
    utilization: float | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GPUContainerUsage:
        """Create GPU container usage from D-Bus dictionary."""
        return cls(
            container=data.get("Container", ""),
            address=data.get("Address", ""),
            memory_used=data.get("MemoryUsed"),
            utilization=data.get("Utilization"),
        )


class GPU(DBusInterface):
    """GPU object for OS Agent."""

    bus_name: str = DBUS_NAME_HAOS
    object_path: str = DBUS_OBJECT_HAOS_GPU

    def __init__(self) -> None:
        """Initialize object."""
        super().__init__()
        # Memory of a GPU doesn't change, so it is read once per address
        self._memory_total: dict[str, int | None] = {}

    @dbus_connected
    async def get_devices(self) -> list[GPUDevice]:
        """Return GPUs of the host with current statistics.

        Requires OS Agent 1.15.0 or newer.
        """
        devices = [
            GPUDevice.from_dict(device)
            for device in await self.connected_dbus.GPU.call("get_devices")
        ]
        self._memory_total.update(
            {device.address: device.memory_total for device in devices}
        )
        return devices

    async def get_memory_total(self, address: str) -> int | None:
        """Return the memory of a GPU in bytes, None if unknown."""
        if address not in self._memory_total:
            await self.get_devices()
        return self._memory_total.get(address)

    @dbus_connected
    async def get_container_usage(self) -> list[GPUContainerUsage]:
        """Return the GPU usage of the processes in containers.

        Requires OS Agent 1.15.0 or newer.
        """
        return [
            GPUContainerUsage.from_dict(usage)
            for usage in await self.connected_dbus.GPU.call("get_container_usage")
        ]
