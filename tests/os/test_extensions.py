"""Test Home Assistant OS system extensions."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from awesomeversion import AwesomeVersion
import pytest

from supervisor.const import CoreState
from supervisor.coresys import CoreSys
from supervisor.exceptions import (
    DBusError as SupervisorDBusError,
    HassOSExtensionBusyError,
    HassOSExtensionError,
    HassOSExtensionsNotSupportedError,
    HassOSUpdateError,
)
from supervisor.os.const import OSExtension
from supervisor.resolution.const import ContextType, IssueType
from supervisor.resolution.data import Issue

from tests.common import MockResponse

# pylint: disable=protected-access

OTA_URL = (
    "https://github.com/home-assistant/operating-system/releases/download/"
    "{version}/{os_name}_{board}-{version}.raucb"
)
RELEASE_URL = "https://github.com/home-assistant/operating-system/releases/download"


def mock_download(websession: MagicMock, content: dict[str, bytes]) -> None:
    """Serve content by URL, unknown URLs return 404."""

    def _get(url: str, **kwargs) -> MockResponse:
        if url not in content:
            return MockResponse(status=404)
        response = MockResponse()
        response.content = MagicMock()
        response.content.read = AsyncMock(side_effect=[content[url], b""])
        return response

    websession.get = MagicMock(side_effect=_get)


@pytest.fixture(name="haos")
async def fixture_haos(
    coresys: CoreSys,
    tmp_supervisor_data: Path,
    path_extern: None,
    supervisor_internet: AsyncMock,
) -> Path:
    """Set up Home Assistant OS 12.0 and return the extensions folder."""
    await coresys.core.set_state(CoreState.RUNNING)
    coresys.os._available = True
    coresys.os._board = "generic-x86-64"
    coresys.os._os_name = "haos"
    coresys.os._version = AwesomeVersion("12.0")
    coresys.updater._data = {
        "ota": OTA_URL,
        "hassos_unrestricted": AwesomeVersion("13.0"),
    }
    return coresys.config.path_os_extensions


def test_extension_download_url(coresys: CoreSys) -> None:
    """Test extension URL is derived from the OTA bundle URL."""
    coresys.os._board = "generic-x86-64"
    coresys.updater._data = {"ota": OTA_URL}

    assert (
        coresys.os.get_extension_download_url(
            OSExtension.NVIDIA_LEGACY, AwesomeVersion("17.0")
        )
        == f"{RELEASE_URL}/17.0/haos_generic-x86-64-17.0.nvidia-legacy.raw"
    )


def test_extension_download_url_invalid_template(coresys: CoreSys) -> None:
    """Test extension URL can't be derived from an OTA URL without bundle suffix."""
    coresys.os._board = "generic-x86-64"
    coresys.updater._data = {"ota": "https://example.com/{version}/{board}.bin"}

    with pytest.raises(HassOSExtensionError):
        coresys.os.get_extension_download_url(
            OSExtension.NVIDIA, AwesomeVersion("17.0")
        )


@pytest.mark.parametrize(
    ("name", "existing"),
    [
        pytest.param(OSExtension.NVIDIA, [], id="fresh"),
        pytest.param(OSExtension.NVIDIA, [OSExtension.NVIDIA], id="reinstall"),
        pytest.param(
            OSExtension.NVIDIA, [OSExtension.NVIDIA_LEGACY], id="replace-legacy"
        ),
        pytest.param(
            OSExtension.NVIDIA_LEGACY, [OSExtension.NVIDIA], id="replace-open"
        ),
    ],
)
async def test_install(
    coresys: CoreSys,
    haos: Path,
    websession: MagicMock,
    name: OSExtension,
    existing: list[OSExtension],
) -> None:
    """Test install downloads the image for the current OS version."""
    haos.mkdir()
    for other in existing:
        (haos / f"{other}.raw").write_bytes(b"old")
    mock_download(
        websession, {f"{RELEASE_URL}/12.0/haos_generic-x86-64-12.0.{name}.raw": b"new"}
    )

    await coresys.os.extensions.install(name)

    assert await coresys.os.extensions.installed() == [name]
    assert (haos / f"{name}.raw").read_bytes() == b"new"
    assert sorted(p.name for p in haos.iterdir()) == [f"{name}.raw"]
    assert Issue(IssueType.REBOOT_REQUIRED, ContextType.SYSTEM) in (
        coresys.resolution.issues
    )


async def test_install_pending_version(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test install targets an installed OS update pending a reboot."""
    coresys.os._version_pending = AwesomeVersion("13.0")
    mock_download(
        websession,
        {f"{RELEASE_URL}/13.0/haos_generic-x86-64-13.0.nvidia.raw": b"new"},
    )

    await coresys.os.extensions.install(OSExtension.NVIDIA)

    assert (haos / "nvidia.raw").read_bytes() == b"new"


async def test_install_download_failure(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test a failed download keeps the installed image and leaves no file behind."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")
    mock_download(websession, {})

    with pytest.raises(HassOSExtensionError, match="404"):
        await coresys.os.extensions.install(OSExtension.NVIDIA)

    assert sorted(p.name for p in haos.iterdir()) == ["nvidia.raw"]
    assert (haos / "nvidia.raw").read_bytes() == b"old"
    assert Issue(IssueType.REBOOT_REQUIRED, ContextType.SYSTEM) not in (
        coresys.resolution.issues
    )


async def test_install_dismisses_update_failed_issue(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test installing an extension dismisses its failed update issue."""
    coresys.resolution.create_issue(
        IssueType.UPDATE_FAILED, ContextType.OS, reference="nvidia"
    )
    mock_download(
        websession, {f"{RELEASE_URL}/12.0/haos_generic-x86-64-12.0.nvidia.raw": b"new"}
    )

    await coresys.os.extensions.install(OSExtension.NVIDIA)

    assert Issue(IssueType.UPDATE_FAILED, ContextType.OS, reference="nvidia") not in (
        coresys.resolution.issues
    )


async def test_remove(coresys: CoreSys, haos: Path) -> None:
    """Test removing an installed extension."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")

    await coresys.os.extensions.remove(OSExtension.NVIDIA)

    assert not (haos / "nvidia.raw").exists()
    assert Issue(IssueType.REBOOT_REQUIRED, ContextType.SYSTEM) in (
        coresys.resolution.issues
    )


@pytest.mark.usefixtures("haos")
async def test_remove_not_installed(coresys: CoreSys) -> None:
    """Test removing an extension which is not installed fails."""
    with pytest.raises(HassOSExtensionError, match="not installed"):
        await coresys.os.extensions.remove(OSExtension.NVIDIA)


@pytest.mark.usefixtures("tmp_supervisor_data", "supervisor_internet")
async def test_not_supported(coresys: CoreSys) -> None:
    """Test extensions are rejected without Home Assistant OS."""
    with pytest.raises(HassOSExtensionsNotSupportedError):
        await coresys.os.extensions.installed()
    with pytest.raises(HassOSExtensionsNotSupportedError):
        await coresys.os.extensions.install(OSExtension.NVIDIA)
    with pytest.raises(HassOSExtensionsNotSupportedError):
        await coresys.os.extensions.remove(OSExtension.NVIDIA)


@pytest.mark.usefixtures("haos")
async def test_change_while_busy(coresys: CoreSys) -> None:
    """Test extension changes are rejected while another change runs."""
    async with coresys.os.extensions._lock:
        with pytest.raises(HassOSExtensionBusyError):
            await coresys.os.extensions.install(OSExtension.NVIDIA)
        with pytest.raises(HassOSExtensionBusyError):
            await coresys.os.extensions.remove(OSExtension.NVIDIA)


async def test_load_removes_staging_files(coresys: CoreSys, haos: Path) -> None:
    """Test leftover downloads are removed on load."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")
    (haos / ".nvidia-13.0.tmp").write_bytes(b"partial")

    await coresys.os.extensions.load()

    assert sorted(p.name for p in haos.iterdir()) == ["nvidia.raw"]


async def fake_download_raucb(url: str, raucb: Path) -> None:
    """Fake download of the OTA bundle."""
    raucb.touch()


async def test_os_update_updates_extensions(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test OS update replaces installed extensions with the new version."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")
    mock_download(
        websession, {f"{RELEASE_URL}/13.0/haos_generic-x86-64-13.0.nvidia.raw": b"new"}
    )

    with patch.object(coresys.os, "_download_raucb", side_effect=fake_download_raucb):
        await coresys.os.update()

    assert coresys.os.version_pending == AwesomeVersion("13.0")
    assert sorted(p.name for p in haos.iterdir()) == ["nvidia.raw"]
    assert (haos / "nvidia.raw").read_bytes() == b"new"


async def test_os_update_extension_download_failure(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test a missing extension image doesn't block the OS update."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")
    mock_download(websession, {})

    with patch.object(coresys.os, "_download_raucb", side_effect=fake_download_raucb):
        await coresys.os.update()

    assert coresys.os.version_pending == AwesomeVersion("13.0")
    assert sorted(p.name for p in haos.iterdir()) == ["nvidia.raw"]
    assert (haos / "nvidia.raw").read_bytes() == b"old"
    assert Issue(IssueType.UPDATE_FAILED, ContextType.OS, reference="nvidia") in (
        coresys.resolution.issues
    )


async def test_os_update_failure_keeps_extensions(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test a failed OS update keeps the extensions of the running OS."""
    haos.mkdir()
    (haos / "nvidia.raw").write_bytes(b"old")
    mock_download(
        websession, {f"{RELEASE_URL}/13.0/haos_generic-x86-64-13.0.nvidia.raw": b"new"}
    )

    with (
        patch.object(coresys.os, "_download_raucb", side_effect=fake_download_raucb),
        patch.object(
            coresys.dbus.rauc, "install", side_effect=SupervisorDBusError("fail")
        ),
        pytest.raises(HassOSUpdateError),
    ):
        await coresys.os.update()

    assert sorted(p.name for p in haos.iterdir()) == ["nvidia.raw"]
    assert (haos / "nvidia.raw").read_bytes() == b"old"
    assert Issue(IssueType.UPDATE_FAILED, ContextType.OS, reference="nvidia") not in (
        coresys.resolution.issues
    )


async def test_install_blocked_during_os_update(
    coresys: CoreSys, haos: Path, websession: MagicMock
) -> None:
    """Test extension changes are rejected while an OS update installs."""
    mock_download(websession, {})
    install_started = asyncio.Event()
    finish_install = asyncio.Event()

    async def slow_install(*args) -> None:
        install_started.set()
        await finish_install.wait()
        raise SupervisorDBusError("fail")

    with (
        patch.object(coresys.os, "_download_raucb", side_effect=fake_download_raucb),
        patch.object(coresys.dbus.rauc, "install", side_effect=slow_install),
    ):
        update = asyncio.create_task(coresys.os.update())
        await install_started.wait()

        with pytest.raises(HassOSExtensionBusyError):
            await coresys.os.extensions.install(OSExtension.NVIDIA)

        finish_install.set()
        with pytest.raises(HassOSUpdateError):
            await update


async def test_installed_ignores_unknown_images(coresys: CoreSys, haos: Path) -> None:
    """Test only known extensions are reported as installed."""
    haos.mkdir()
    (haos / "custom.raw").write_bytes(b"custom")
    (haos / "nvidia-legacy.raw").write_bytes(b"old")

    assert await coresys.os.extensions.installed() == [OSExtension.NVIDIA_LEGACY]
