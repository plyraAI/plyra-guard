"""
Stdout Exporter
~~~~~~~~~~~~~~~

Writes audit entries as JSON lines to stdout.
"""

from __future__ import annotations

import json
import sys

from plyra_guard.core.intent import AuditEntry

__all__ = ["StdoutExporter"]


class StdoutExporter:
    """
    Default exporter that writes audit entries as JSON lines to stdout.

    Each entry is serialized as a single JSON line for easy piping
    to log aggregators.
    """

    def __init__(self, stream: object | None = None, pretty: bool = False) -> None:
        self._stream = stream or sys.stdout
        self._pretty = pretty

    def export(self, entry: AuditEntry) -> None:
        """Write the entry as a JSON line to the output stream."""
        data = entry.to_dict()
        if self._pretty:
            line = json.dumps(data, indent=2, default=str)
        else:
            line = json.dumps(data, default=str)
        self._stream.write(line + "\n")  # type: ignore[union-attr]
        self._stream.flush()  # type: ignore[union-attr]
