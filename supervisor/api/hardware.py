"""Init file for Supervisor hardware RESTful API."""

import logging
from typing import Any

from aiohttp import web

from ..const import (
    ATTR_ADDRESS,
    ATTR_AUDIO,
    ATTR_DEVICES,
    ATTR_ID,
    ATTR_INPUT,
    ATTR_NAME,
    ATTR_OUTPUT,
    ATTR_SERIAL,
    ATTR_SIZE,
    ATTR_SYSTEM,
)
from ..coresys import CoreSysAttributes
from ..dbus.agent.gpu import GPUDevice
from ..dbus.udisks2 import UDisks2Manager
from ..dbus.udisks2.block import UDisks2Block
from ..dbus.udisks2.drive import UDisks2Drive
from ..hardware.data import Device
from .const import (
    ATTR_ATTRIBUTES,
    ATTR_BY_ID,
    ATTR_CHILDREN,
    ATTR_CONNECTION_BUS,
    ATTR_DEV_PATH,
    ATTR_DEVICE,
    ATTR_DRIVER,
    ATTR_DRIVER_VERSION,
    ATTR_DRIVES,
    ATTR_EJECTABLE,
    ATTR_FILESYSTEMS,
    ATTR_GPUS,
    ATTR_MEMORY_TOTAL,
    ATTR_MEMORY_USED,
    ATTR_MODEL,
    ATTR_MOUNT_POINTS,
    ATTR_POWER,
    ATTR_REMOVABLE,
    ATTR_REVISION,
    ATTR_SEAT,
    ATTR_SUBSYSTEM,
    ATTR_SYSFS,
    ATTR_TEMPERATURE,
    ATTR_TIME_DETECTED,
    ATTR_UTILIZATION,
    ATTR_VENDOR,
)
from .utils import api_process

_LOGGER: logging.Logger = logging.getLogger(__name__)


def device_struct(device: Device) -> dict[str, Any]:
    """Return a dict with information of a interface to be used in the API."""
    return {
        ATTR_NAME: device.name,
        ATTR_SYSFS: device.sysfs,
        ATTR_DEV_PATH: device.path,
        ATTR_SUBSYSTEM: device.subsystem,
        ATTR_BY_ID: device.by_id,
        ATTR_ATTRIBUTES: device.attributes,
        ATTR_CHILDREN: device.children,
    }


def filesystem_struct(fs_block: UDisks2Block) -> dict[str, Any]:
    """Return a dict with information of a filesystem block device to be used in the API."""
    return {
        ATTR_DEVICE: str(fs_block.device),
        ATTR_ID: fs_block.id,
        ATTR_SIZE: fs_block.size,
        ATTR_NAME: fs_block.id_label,
        ATTR_SYSTEM: fs_block.hint_system,
        ATTR_MOUNT_POINTS: [
            str(mount_point)
            for mount_point in (
                fs_block.filesystem.mount_points if fs_block.filesystem else []
            )
        ],
    }


def drive_struct(udisks2: UDisks2Manager, drive: UDisks2Drive) -> dict[str, Any]:
    """Return a dict with information of a disk to be used in the API."""
    return {
        ATTR_VENDOR: drive.vendor,
        ATTR_MODEL: drive.model,
        ATTR_REVISION: drive.revision,
        ATTR_SERIAL: drive.serial,
        ATTR_ID: drive.id,
        ATTR_SIZE: drive.size,
        ATTR_TIME_DETECTED: drive.time_detected.isoformat(),
        ATTR_CONNECTION_BUS: drive.connection_bus,
        ATTR_SEAT: drive.seat,
        ATTR_REMOVABLE: drive.removable,
        ATTR_EJECTABLE: drive.ejectable,
        ATTR_FILESYSTEMS: [
            filesystem_struct(block)
            for block in udisks2.block_devices
            if block.filesystem and block.drive == drive.object_path
        ],
    }


def gpu_struct(gpu: GPUDevice) -> dict[str, Any]:
    """Return a dict with information and statistics of a GPU for the API."""
    return {
        ATTR_ADDRESS: gpu.address,
        ATTR_VENDOR: gpu.vendor,
        ATTR_NAME: gpu.name,
        ATTR_DRIVER: gpu.driver,
        ATTR_DRIVER_VERSION: gpu.driver_version,
        ATTR_UTILIZATION: gpu.utilization,
        ATTR_MEMORY_USED: gpu.memory_used,
        ATTR_MEMORY_TOTAL: gpu.memory_total,
        ATTR_TEMPERATURE: gpu.temperature,
        ATTR_POWER: gpu.power,
    }


class APIHardware(CoreSysAttributes):
    """Handle RESTful API for hardware functions."""

    @api_process
    async def info(self, request: web.Request) -> dict[str, Any]:
        """Show hardware info."""
        return {
            ATTR_DEVICES: [
                device_struct(device) for device in self.sys_hardware.devices
            ],
            ATTR_DRIVES: [
                drive_struct(self.sys_dbus.udisks2, drive)
                for drive in self.sys_dbus.udisks2.drives
            ],
        }

    @api_process
    async def audio(self, request: web.Request) -> dict[str, Any]:
        """Show pulse audio profiles."""
        return {
            ATTR_AUDIO: {
                ATTR_INPUT: {
                    profile.name: profile.description
                    for profile in self.sys_host.sound.inputs
                },
                ATTR_OUTPUT: {
                    profile.name: profile.description
                    for profile in self.sys_host.sound.outputs
                },
            }
        }

    @api_process
    async def gpu(self, request: web.Request) -> dict[str, Any]:
        """Show GPUs of the host with current statistics."""
        if not self.sys_dbus.agent.gpu.is_connected:
            return {ATTR_GPUS: []}

        return {
            ATTR_GPUS: [
                gpu_struct(gpu) for gpu in await self.sys_dbus.agent.gpu.get_devices()
            ]
        }
