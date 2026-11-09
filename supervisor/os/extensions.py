"""System extension images merged into /usr by Home Assistant OS at boot."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
from pathlib import Path

from awesomeversion import AwesomeVersion

from ..coresys import CoreSys, CoreSysAttributes
from ..exceptions import (
    HassOSError,
    HassOSExtensionBusyError,
    HassOSExtensionError,
    HassOSExtensionsNotSupportedError,
    HassOSJobError,
)
from ..jobs.const import JobCondition
from ..jobs.decorator import Job
from ..resolution.const import ContextType, IssueType, SuggestionType
from ..resolution.data import Issue
from .const import OS_EXTENSION_EXCLUSIVE_GROUPS, OSExtension

_LOGGER: logging.Logger = logging.getLogger(__name__)

# Staging files must not end in .raw, the OS merges every *.raw at boot
STAGING_SUFFIX = ".tmp"


@dataclass(slots=True)
class StagedExtensions:
    """Extension images downloaded for an OS version, not yet activated."""

    version: AwesomeVersion
    files: dict[OSExtension, Path] = field(default_factory=dict)
    failed: list[OSExtension] = field(default_factory=list)


class OSExtensions(CoreSysAttributes):
    """Manage the system extension images in the Supervisor data folder.

    Each image pins the exact OS version it was built for, the OS ignores it
    on any other version. Changes take effect on the next boot.
    """

    def __init__(self, coresys: CoreSys) -> None:
        """Initialize OS extensions handler."""
        self.coresys: CoreSys = coresys
        self._lock = asyncio.Lock()

    @property
    def available(self) -> list[OSExtension]:
        """Return extensions which can be installed."""
        return list(OSExtension)

    def _path(self, name: OSExtension) -> Path:
        """Return path the OS loads an extension image from."""
        return self.sys_config.path_os_extensions / f"{name}.raw"

    def _staging_path(self, name: OSExtension, version: AwesomeVersion) -> Path:
        """Return temporary download path for an extension image."""
        return (
            self.sys_config.path_os_extensions / f".{name}-{version!s}{STAGING_SUFFIX}"
        )

    def _check_supported(self) -> None:
        """Raise if OS extensions can't be used on this system."""
        if not self.sys_os.available:
            raise HassOSExtensionsNotSupportedError(_LOGGER.error)

    def _check_not_busy(self) -> None:
        """Raise if an extension change or OS update is in progress."""
        if self._lock.locked():
            raise HassOSExtensionBusyError(_LOGGER.warning)

    def _installed(self) -> list[OSExtension]:
        """Return installed extensions, must run in executor."""
        return [name for name in OSExtension if self._path(name).is_file()]

    async def installed(self) -> list[OSExtension]:
        """Return installed extensions."""
        self._check_supported()
        return await self.sys_run_in_executor(self._installed)

    def _remove_staging_files(self) -> None:
        """Remove downloads left behind by an interrupted install, must run in executor."""
        if not self.sys_config.path_os_extensions.is_dir():
            return
        for path in self.sys_config.path_os_extensions.glob(f".*{STAGING_SUFFIX}"):
            path.unlink(missing_ok=True)

    async def load(self) -> None:
        """Clean up after an interrupted extension download."""
        if not self.sys_os.available:
            return
        try:
            await self.sys_run_in_executor(self._remove_staging_files)
        except OSError as err:
            self.sys_resolution.check_oserror(err)
            _LOGGER.warning("Can't clean up OS extension downloads: %s", err)

    async def _download(self, name: OSExtension, version: AwesomeVersion) -> Path:
        """Download extension image for version to its staging path."""
        url = self.sys_os.get_extension_download_url(name, version)
        staging = self._staging_path(name, version)
        try:
            await self.sys_run_in_executor(
                lambda: self.sys_config.path_os_extensions.mkdir(exist_ok=True)
            )
        except OSError as err:
            self.sys_resolution.check_oserror(err)
            raise HassOSExtensionError(
                f"Can't create OS extensions folder: {err!s}", _LOGGER.error
            ) from err

        try:
            await self.sys_os.download_file(
                url, staging, label=f"OS extension {name}", error=HassOSExtensionError
            )
        except HassOSExtensionError:
            await self.sys_run_in_executor(lambda: staging.unlink(missing_ok=True))
            raise
        return staging

    async def _activate(self, name: OSExtension, staging: Path) -> None:
        """Move a downloaded image in place atomically."""
        try:
            await self.sys_run_in_executor(staging.replace, self._path(name))
        except OSError as err:
            self.sys_resolution.check_oserror(err)
            raise HassOSExtensionError(
                f"Can't install OS extension {name}: {err!s}", _LOGGER.error
            ) from err

        self._dismiss_update_failed(name)

    async def _unlink(self, name: OSExtension) -> None:
        """Remove an installed extension image."""
        try:
            await self.sys_run_in_executor(self._path(name).unlink)
        except OSError as err:
            self.sys_resolution.check_oserror(err)
            raise HassOSExtensionError(
                f"Can't remove OS extension {name}: {err!s}", _LOGGER.error
            ) from err

        self._dismiss_update_failed(name)

    def _dismiss_update_failed(self, name: OSExtension) -> None:
        """Dismiss the issue of an earlier failed update of an extension."""
        issue = Issue(IssueType.UPDATE_FAILED, ContextType.OS, reference=name)
        if existing := self.sys_resolution.get_issue_if_present(issue):
            self.sys_resolution.dismiss_issue(existing)

    def _create_reboot_issue(self) -> None:
        self.sys_resolution.create_issue(
            IssueType.REBOOT_REQUIRED,
            ContextType.SYSTEM,
            suggestions=[SuggestionType.EXECUTE_REBOOT],
        )

    @Job(
        name="os_extensions_install",
        conditions=[JobCondition.INTERNET_SYSTEM],
        on_condition=HassOSJobError,
    )
    async def install(self, name: OSExtension) -> None:
        """Install extension for the OS version booted next."""
        self._check_supported()
        self._check_not_busy()

        # An installed update activates on the next boot, so the image has to
        # match the pending version
        version = self.sys_os.version_pending or self.sys_os.version
        if version is None:
            raise HassOSExtensionError(
                "Can't determine OS version for OS extension", _LOGGER.error
            )

        async with self._lock:
            staging = await self._download(name, version)
            await self._activate(name, staging)
            _LOGGER.info(
                "Installed OS extension %s for OS %s; reboot required", name, version
            )

            for group in OS_EXTENSION_EXCLUSIVE_GROUPS:
                if name not in group:
                    continue
                for other in group - {name}:
                    if await self.sys_run_in_executor(self._path(other).is_file):
                        await self._unlink(other)
                        _LOGGER.info("Removed conflicting OS extension %s", other)

        self._create_reboot_issue()

    @Job(name="os_extensions_remove", on_condition=HassOSJobError)
    async def remove(self, name: OSExtension) -> None:
        """Remove an installed extension."""
        self._check_supported()
        self._check_not_busy()

        async with self._lock:
            if not await self.sys_run_in_executor(self._path(name).is_file):
                raise HassOSExtensionError(
                    f"OS extension {name} is not installed", _LOGGER.warning
                )
            await self._unlink(name)
            _LOGGER.info("Removed OS extension %s; reboot required", name)

        self._create_reboot_issue()

    @asynccontextmanager
    async def prepare_update(
        self, version: AwesomeVersion
    ) -> AsyncIterator[StagedExtensions]:
        """Download installed extensions for an OS update.

        Blocks extension changes until the context exits. Call commit_update
        inside the context once the OS update is installed, staged images not
        committed by then are discarded.
        """
        async with self._lock:
            staged = StagedExtensions(version)
            try:
                for name in await self.sys_run_in_executor(self._installed):
                    try:
                        staged.files[name] = await self._download(name, version)
                    except HassOSError as err:
                        _LOGGER.error(
                            "Can't download OS extension %s for OS %s: %s",
                            name,
                            version,
                            err,
                        )
                        staged.failed.append(name)
                yield staged
            finally:
                for staging in staged.files.values():
                    await self.sys_run_in_executor(
                        lambda path=staging: path.unlink(missing_ok=True)
                    )

    async def commit_update(self, staged: StagedExtensions) -> None:
        """Activate extension images downloaded for an installed OS update."""
        for name, staging in staged.files.items():
            try:
                await self._activate(name, staging)
            except HassOSExtensionError:
                staged.failed.append(name)

        for name in staged.failed:
            _LOGGER.error(
                "OS extension %s is not available for OS %s, install it again "
                "after the reboot",
                name,
                staged.version,
            )
            self.sys_resolution.create_issue(
                IssueType.UPDATE_FAILED, ContextType.OS, reference=name
            )
