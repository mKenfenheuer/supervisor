"""Constants for OS."""

from enum import StrEnum

FILESYSTEM_LABEL_DATA_DISK = "hassos-data"
FILESYSTEM_LABEL_DISABLED_DATA_DISK = "hassos-data-dis"
FILESYSTEM_LABEL_OLD_DATA_DISK = "hassos-data-old"
PARTITION_NAME_EXTERNAL_DATA_DISK = "hassos-data-external"
PARTITION_NAME_OLD_EXTERNAL_DATA_DISK = "hassos-data-external-old"

# Minimum a single GPT partition can lose: 1 MiB start alignment plus the
# backup GPT header and entries (33 sectors of 512 bytes) at the end
GPT_PARTITION_MIN_OVERHEAD = 1024 * 1024 + 33 * 512


class OSExtension(StrEnum):
    """System extension images published with Home Assistant OS releases."""

    NVIDIA = "nvidia"
    NVIDIA_LEGACY = "nvidia-legacy"


# Variants providing the same driver stack, only one of each can be installed
OS_EXTENSION_EXCLUSIVE_GROUPS: tuple[frozenset[OSExtension], ...] = (
    frozenset({OSExtension.NVIDIA, OSExtension.NVIDIA_LEGACY}),
)
