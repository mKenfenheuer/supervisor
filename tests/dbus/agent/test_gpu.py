"""Test GPU/Agent dbus interface."""

from dbus_fast import DBusError, ErrorType
from dbus_fast.aio.message_bus import MessageBus
import pytest

from supervisor.dbus.agent import OSAgent
from supervisor.dbus.agent.gpu import GPUDevice
from supervisor.exceptions import DBusError as SupervisorDBusError

from tests.dbus_service_mocks.agent_gpu import GPU as GPUService
from tests.dbus_service_mocks.base import DBusServiceMock


@pytest.fixture(name="gpu_service")
async def fixture_gpu_service(
    os_agent_services: dict[str, DBusServiceMock],
) -> GPUService:
    """Mock GPU dbus service."""
    return os_agent_services["agent_gpu"]


@pytest.mark.parametrize("os_agent_version", ["1.15.0"], indirect=True)
@pytest.mark.usefixtures("os_agent_version")
async def test_dbus_osagent_gpu_devices(
    gpu_service: GPUService, dbus_session_bus: MessageBus
):
    """Test GPU devices with statistics from the host."""
    os_agent = OSAgent()
    await os_agent.connect(dbus_session_bus)

    assert os_agent.gpu.is_connected
    assert await os_agent.gpu.get_devices() == [
        GPUDevice(
            address="0000:01:00.0",
            vendor="nvidia",
            name="NVIDIA GeForce RTX 3090",
            driver="nvidia",
            driver_version="615.78.08",
            utilization=7.0,
            memory_used=2982150144,
            memory_total=25769803776,
            temperature=34.0,
            power=16.37,
        ),
        GPUDevice(
            address="0000:00:02.0",
            vendor="intel",
            name="Intel GPU [8086:46a6]",
            driver="i915",
            driver_version="6.18.60-haos",
            utilization=None,
            memory_used=None,
            memory_total=None,
            temperature=None,
            power=None,
        ),
    ]
    assert gpu_service.GetDevices.calls == [()]

    gpu_service.response_get_devices = DBusError(ErrorType.FAILED, "nvidia-smi")
    with pytest.raises(SupervisorDBusError):
        await os_agent.gpu.get_devices()


@pytest.mark.usefixtures("os_agent_services")
async def test_dbus_osagent_gpu_old_os_agent(dbus_session_bus: MessageBus):
    """Test GPU interface is not connected with OS Agent before 1.15.0."""
    os_agent = OSAgent()
    await os_agent.connect(dbus_session_bus)

    assert os_agent.is_connected
    assert not os_agent.gpu.is_connected
