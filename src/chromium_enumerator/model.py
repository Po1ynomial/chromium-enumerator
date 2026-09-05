from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

EvidenceCategory = Literal["engine", "electron-marker", "resource", "helper", "executable"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Evidence:
    category: EvidenceCategory
    path: Path
    reason: str
    family_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "path": str(self.path),
            "reason": self.reason,
            "family_hint": self.family_hint,
        }


@dataclass
class RuntimeResult:
    root: Path
    family: str
    confidence: Confidence
    evidence: list[Evidence] = field(default_factory=list)
    entrypoints: list[Path] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "family": self.family,
            "confidence": self.confidence,
            "evidence": [item.to_dict() for item in self.evidence],
            "entrypoints": [str(path) for path in self.entrypoints],
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
        }
