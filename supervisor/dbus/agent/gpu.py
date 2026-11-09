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


class GPU(DBusInterface):
    """GPU object for OS Agent."""

    bus_name: str = DBUS_NAME_HAOS
    object_path: str = DBUS_OBJECT_HAOS_GPU

    @dbus_connected
    async def get_devices(self) -> list[GPUDevice]:
        """Return GPUs of the host with current statistics.

        Requires OS Agent 1.15.0 or newer.
        """
        return [
            GPUDevice.from_dict(device)
            for device in await self.connected_dbus.GPU.call("get_devices")
        ]
