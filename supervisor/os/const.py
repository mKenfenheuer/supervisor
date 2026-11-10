"""Constants for OS."""

FILESYSTEM_LABEL_DATA_DISK = "hassos-data"
FILESYSTEM_LABEL_DISABLED_DATA_DISK = "hassos-data-dis"
FILESYSTEM_LABEL_OLD_DATA_DISK = "hassos-data-old"
PARTITION_NAME_EXTERNAL_DATA_DISK = "hassos-data-external"
PARTITION_NAME_OLD_EXTERNAL_DATA_DISK = "hassos-data-external-old"

# OS variants per board. A variant shares the root file system of its board
# and adds a system extension (e.g. the NVIDIA driver), its update bundle is
# haos_<board>-<variant>-<version>.raucb.
OS_VARIANTS: dict[str, tuple[str, ...]] = {
    "generic-x86-64": ("nvidia", "nvidia-legacy"),
    "ova": ("nvidia", "nvidia-legacy"),
}

# Minimum a single GPT partition can lose: 1 MiB start alignment plus the
# backup GPT header and entries (33 sectors of 512 bytes) at the end
GPT_PARTITION_MIN_OVERHEAD = 1024 * 1024 + 33 * 512
