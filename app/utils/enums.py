from enum import Enum


class ImageType(str, Enum):
    """Supported image origins."""

    MIRRORED = "mirrored"
    CUSTOM = "custom"


class ImageStatus(str, Enum):
    """Lifecycle status for tracked images."""

    PENDING = "pending"
    MIRRORING = "mirroring"
    READY = "ready"
    ERROR = "error"


class JobStatus(str, Enum):
    """Lifecycle states for background mirror jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
