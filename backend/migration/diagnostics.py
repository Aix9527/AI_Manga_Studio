from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosticResult:
    overall: str = "pass"  # pass | warn | fail
    python_version: str = ""
    node_version: str = ""
    npm_version: str = ""
    npm_path: str = ""
    comfyui_available: bool = False
    ffmpeg_available: bool = False
    ffprobe_available: bool = False
    disk_free_gb: float = 0.0
    ram_total_gb: float = 0.0
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class EnvironmentDiagnostics:
    def run(self) -> DiagnosticResult:
        result = DiagnosticResult()

        result.python_version = platform.python_version()

        result.node_version, result.npm_version, result.npm_path = self._check_node()
        if not result.npm_path:
            result.issues.append("npm not found. Install Node.js from https://nodejs.org")

        result.comfyui_available = self._check_comfyui()
        if not result.comfyui_available:
            result.warnings.append("ComfyUI not reachable at http://127.0.0.1:8188")

        result.ffmpeg_available = shutil.which("ffmpeg") is not None
        result.ffprobe_available = shutil.which("ffprobe") is not None
        if not result.ffmpeg_available:
            result.issues.append("ffmpeg not found on PATH")

        result.disk_free_gb = self._disk_free()
        if result.disk_free_gb < 5.0:
            result.warnings.append(f"Low disk space: {result.disk_free_gb:.1f}GB free")

        result.ram_total_gb = self._ram_total()

        if result.issues:
            result.overall = "fail"
        elif result.warnings:
            result.overall = "warn"

        return result

    def report(self, result: DiagnosticResult) -> str:
        lines = [
            "=" * 50,
            "V5 Environment Diagnostics",
            "=" * 50,
            f"Overall    : {result.overall.upper()}",
            f"Python     : {result.python_version}",
            f"Node       : {result.node_version or 'not found'}",
            f"npm        : {result.npm_path or 'not found'}",
            f"ComfyUI    : {'OK' if result.comfyui_available else 'NOT REACHABLE'}",
            f"ffmpeg     : {'OK' if result.ffmpeg_available else 'NOT FOUND'}",
            f"ffprobe    : {'OK' if result.ffprobe_available else 'NOT FOUND'}",
            f"Disk Free  : {result.disk_free_gb:.1f} GB",
            f"RAM Total  : {result.ram_total_gb:.1f} GB",
            "",
        ]

        if result.issues:
            lines.append("ISSUES (blocking):")
            for i in result.issues:
                lines.append(f"  - {i}")
            lines.append("")

        if result.warnings:
            lines.append("WARNINGS:")
            for w in result.warnings:
                lines.append(f"  - {w}")
            lines.append("")

        return "\n".join(lines)

    def _check_node(self) -> tuple[str, str, str]:
        for cmd in ["node", "node.exe"]:
            node_path = shutil.which(cmd)
            if node_path:
                break
        else:
            return ("", "", "")

        try:
            node_v = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
            npm_v = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=10)
            npm_p = shutil.which("npm") or ""
            return (node_v.stdout.strip(), npm_v.stdout.strip(), npm_p)
        except Exception:
            return ("", "", "")

    def _check_comfyui(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8188/system_stats", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _disk_free(self) -> float:
        try:
            usage = shutil.disk_usage(".")
            return usage.free / (1024**3)
        except Exception:
            return 0.0

    def _ram_total(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().total / (1024**3)
        except ImportError:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                mem_status = ctypes.c_longlong(), ctypes.c_longlong(), ctypes.c_longlong(), ctypes.c_longlong()
                kernel32.GlobalMemoryStatusEx(ctypes.byref(ctypes.c_ulonglong(64)))
                return 0.0
            except Exception:
                return 0.0
