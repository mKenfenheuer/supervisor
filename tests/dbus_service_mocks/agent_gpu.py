"""Mock of OS Agent GPU dbus service."""

from dbus_fast import DBusError, Variant

from .base import DBusServiceMock, dbus_method

BUS_NAME = "io.hass.os"


def setup(object_path: str | None = None) -> DBusServiceMock:
    """Create dbus mock object."""
    return GPU()


class GPU(DBusServiceMock):
    """GPU mock.

    gdbus introspect --system --dest io.hass.os --object-path /io/hass/os/GPU
    """

    object_path = "/io/hass/os/GPU"
    interface = "io.hass.os.GPU"
    response_get_devices: list[dict[str, Variant]] | DBusError = [
        {
            "Address": Variant("s", "0000:01:00.0"),
            "Vendor": Variant("s", "nvidia"),
            "Name": Variant("s", "NVIDIA GeForce RTX 3090"),
            "Driver": Variant("s", "nvidia"),
            "DriverVersion": Variant("s", "615.78.08"),
            "Utilization": Variant("d", 7.0),
            "MemoryUsed": Variant("t", 2982150144),
            "MemoryTotal": Variant("t", 25769803776),
            "Temperature": Variant("d", 34.0),
            "Power": Variant("d", 16.37),
        },
        {
            "Address": Variant("s", "0000:00:02.0"),
            "Vendor": Variant("s", "intel"),
            "Name": Variant("s", "Intel GPU [8086:46a6]"),
            "Driver": Variant("s", "i915"),
            "DriverVersion": Variant("s", "6.18.60-haos"),
        },
    ]

    response_get_container_usage: list[dict[str, Variant]] | DBusError = [
        {
            "Container": Variant(
                "s", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            ),
            "Address": Variant("s", "0000:01:00.0"),
            "MemoryUsed": Variant("t", 2405433344),
            "Utilization": Variant("d", 42.0),
        },
        {
            "Container": Variant(
                "s", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            ),
            "Address": Variant("s", "0000:01:00.0"),
            "MemoryUsed": Variant("t", 954204160),
        },
    ]

    @dbus_method()
    def GetContainerUsage(self) -> "aa{sv}":
        """Get GPU usage per container."""
        if isinstance(self.response_get_container_usage, DBusError):
            raise self.response_get_container_usage  # pylint: disable=raising-bad-type
        return self.response_get_container_usage

    @dbus_method()
    def GetDevices(self) -> "aa{sv}":
        """Get GPU devices."""
        if isinstance(self.response_get_devices, DBusError):
            raise self.response_get_devices  # pylint: disable=raising-bad-type
        return self.response_get_devices
