"""Test Docker API."""

from pathlib import Path

from aiohttp.test_utils import TestClient
from dbus_fast.aio.message_bus import MessageBus
import pytest

from supervisor.coresys import CoreSys
from supervisor.hardware.data import Device


async def test_api_hardware_info(api_client_with_prefix: tuple[TestClient, str]):
    """Test docker info api."""
    api_client, prefix = api_client_with_prefix
    resp = await api_client.get(f"{prefix}/hardware/info")
    result = await resp.json()

    assert result["result"] == "ok"


async def test_api_hardware_info_device(
    api_client_with_prefix: tuple[TestClient, str], coresys: CoreSys
):
    """Test docker info api."""
    api_client, prefix = api_client_with_prefix
    coresys.hardware.update_device(
        Device(
            "sda",
            Path("/dev/sda"),
            Path("/sys/bus/usb/000"),
            "sound",
            None,
            [Path("/dev/serial/by-id/test")],
            {"ID_NAME": "xy"},
            [],
        )
    )

    resp = await api_client.get(f"{prefix}/hardware/info")
    result = await resp.json()

    assert result["result"] == "ok"
    assert result["data"]["devices"][-1]["name"] == "sda"
    assert result["data"]["devices"][-1]["by_id"] == "/dev/serial/by-id/test"


async def test_api_hardware_info_drives(
    api_client_with_prefix: tuple[TestClient, str], coresys: CoreSys
):
    """Test drive info."""
    api_client, prefix = api_client_with_prefix
    await coresys.dbus.udisks2.connect(coresys.dbus.bus)

    resp = await api_client.get(f"{prefix}/hardware/info")
    result = await resp.json()

    assert result["result"] == "ok"
    assert {
        drive["id"]: {fs["id"] for fs in drive["filesystems"]}
        for drive in result["data"]["drives"]
    } == {
        "BJTD4R-0x97cde291": {
            "by-id-mmc-BJTD4R_0x97cde291-part1",
            "by-id-mmc-BJTD4R_0x97cde291-part3",
        },
        "SSK-SSK-Storage-DF56419883D56": {
            "by-id-usb-SSK_SSK_Storage_DF56419883D56-0:0-part1"
        },
        "Generic-Flash-Disk-61BCDDB6": {"by-uuid-2802-1EDE"},
    }


@pytest.mark.parametrize("os_agent_version", ["1.15.0"], indirect=True)
@pytest.mark.usefixtures("os_agent_version")
async def test_api_hardware_gpu(
    api_client_with_prefix: tuple[TestClient, str],
    coresys: CoreSys,
    dbus_session_bus: MessageBus,
):
    """Test GPU api returns devices with statistics."""
    await coresys.dbus.agent.connect(dbus_session_bus)
    api_client, prefix = api_client_with_prefix

    resp = await api_client.get(f"{prefix}/hardware/gpu")
    result = await resp.json()

    assert result["result"] == "ok"
    assert result["data"]["gpus"] == [
        {
            "address": "0000:01:00.0",
            "vendor": "nvidia",
            "name": "NVIDIA GeForce RTX 3090",
            "driver": "nvidia",
            "driver_version": "615.78.08",
            "utilization": 7.0,
            "memory_used": 2982150144,
            "memory_total": 25769803776,
            "temperature": 34.0,
            "power": 16.37,
        },
        {
            "address": "0000:00:02.0",
            "vendor": "intel",
            "name": "Intel GPU [8086:46a6]",
            "driver": "i915",
            "driver_version": "6.18.60-haos",
            "utilization": None,
            "memory_used": None,
            "memory_total": None,
            "temperature": None,
            "power": None,
        },
    ]


async def test_api_hardware_gpu_no_os_agent_support(
    api_client_with_prefix: tuple[TestClient, str],
):
    """Test GPU api is empty without GPU support in OS Agent."""
    api_client, prefix = api_client_with_prefix

    resp = await api_client.get(f"{prefix}/hardware/gpu")
    result = await resp.json()

    assert result["result"] == "ok"
    assert result["data"]["gpus"] == []
