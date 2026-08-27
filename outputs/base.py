from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from storage.state import StateStore


class DeliveryStatus(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"      # already delivered / idempotency
    PREVIEW = "preview"      # dry-run / no --push, payload built but not sent
    FAILED = "failed"


class DeliveryError(str, Enum):
    INVALID_WEBHOOK = "INVALID_WEBHOOK"
    SIGNATURE_ERROR = "SIGNATURE_ERROR"
    KEYWORD_REJECTED = "KEYWORD_REJECTED"
    IP_REJECTED = "IP_REJECTED"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    UNKNOWN = "UNKNOWN"


@dataclass
class DeliveryResult:
    target: str
    success: bool
    status: str = "failed"
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    attempts: int = 0
    duration_ms: int = 0
    detail: Optional[dict] = None

    def to_log(self) -> str:
        if self.success:
            return f"[deliver:{self.target}] {self.status}"
        return f"[deliver:{self.target}] FAILED {self.error_type}: {self.error_message}"


@dataclass
class DeliveryContext:
    radar: str
    report_id: str
    title: str
    env: str = "prod"
    dry_run: bool = False
    force: bool = False
    state: Optional[StateStore] = None


class BaseOutput(ABC):
    target: str = "base"

    @abstractmethod
    def deliver(self, report, context: DeliveryContext) -> DeliveryResult:
        ...
