"""
AI Manga Studio Pro V1.0 — System Monitor Routes

Endpoints:
    GET /api/monitor/gpu       → GPU utilization, VRAM, temperature
    GET /api/monitor/cpu       → CPU usage, cores
    GET /api/monitor/ram       → RAM usage
    GET /api/monitor/disk      → Disk space
    GET /api/monitor/queue     → ComfyUI queue status
    GET /api/monitor/overview  → All metrics in one call
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/monitor", tags=["Monitor"])


# --- Models ---

class GPUMetricsResponse(BaseModel):
    """GPU metrics."""
    name: str = ""
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    vram_free_mb: int = 0
    vram_usage_pct: float = 0.0
    utilization_pct: float = 0.0
    temperature_c: float = 0.0
    power_watts: float = 0.0
    is_idle: bool = True


class CPUMetricsResponse(BaseModel):
    """CPU metrics."""
    model: str = ""
    cores_physical: int = 0
    cores_logical: int = 0
    usage_pct: float = 0.0
    per_core_pct: List[float] = Field(default_factory=list)
    frequency_mhz: float = 0.0


class RAMMetricsResponse(BaseModel):
    """RAM metrics."""
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    usage_pct: float = 0.0


class DiskMetricsResponse(BaseModel):
    """Disk metrics."""
    path: str = ""
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    usage_pct: float = 0.0


class QueueMetricsResponse(BaseModel):
    """ComfyUI queue metrics."""
    running: int = 0
    pending: int = 0
    done_today: int = 0
    failed_today: int = 0


class OverviewResponse(BaseModel):
    """System overview."""
    timestamp: str = ""
    gpu: GPUMetricsResponse = Field(default_factory=GPUMetricsResponse)
    cpu: CPUMetricsResponse = Field(default_factory=CPUMetricsResponse)
    ram: RAMMetricsResponse = Field(default_factory=RAMMetricsResponse)
    disk: DiskMetricsResponse = Field(default_factory=DiskMetricsResponse)
    queue: QueueMetricsResponse = Field(default_factory=QueueMetricsResponse)
    is_ready: bool = False  # True if GPU is available and idle


# --- Helpers ---

def _parse_gpu_info() -> GPUMetricsResponse:
    """Parse GPU info via nvidia-smi."""
    import subprocess

    metrics = GPUMetricsResponse()

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return metrics

        line = result.stdout.strip().split(",")

        if len(line) >= 7:
            vram_total = int(float(line[1].strip()))
            vram_used = int(float(line[2].strip()))
            vram_free = int(float(line[3].strip()))

            metrics.name = line[0].strip()
            metrics.vram_total_mb = vram_total
            metrics.vram_used_mb = vram_used
            metrics.vram_free_mb = vram_free
            metrics.vram_usage_pct = round(vram_used / vram_total * 100, 1) if vram_total else 0
            metrics.utilization_pct = float(line[4].strip())
            metrics.temperature_c = float(line[5].strip())
            metrics.power_watts = float(line[6].strip())
            metrics.is_idle = metrics.utilization_pct < 10.0

    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        pass

    return metrics


def _parse_cpu_info() -> CPUMetricsResponse:
    """Parse CPU info."""
    cpu = psutil.cpu_freq()
    return CPUMetricsResponse(
        model=psutil.cpu_info() if hasattr(psutil, "cpu_info") else "Unknown",
        cores_physical=psutil.cpu_count(logical=False),
        cores_logical=psutil.cpu_count(logical=True),
        usage_pct=round(psutil.cpu_percent(interval=0.5), 1),
        per_core_pct=[round(x, 1) for x in psutil.cpu_percent(percpu=True, interval=0.1)],
        frequency_mhz=round(cpu.current, 0) if cpu else 0.0,
    )


def _parse_ram_info() -> RAMMetricsResponse:
    """Parse RAM info."""
    mem = psutil.virtual_memory()
    return RAMMetricsResponse(
        total_gb=round(mem.total / (1024**3), 1),
        used_gb=round(mem.used / (1024**3), 1),
        free_gb=round(mem.available / (1024**3), 1),
        usage_pct=round(mem.percent, 1),
    )


def _parse_disk_info(path: str = "D:") -> DiskMetricsResponse:
    """Parse disk info."""
    usage = psutil.disk_usage(path)
    return DiskMetricsResponse(
        path=path,
        total_gb=round(usage.total / (1024**3), 1),
        used_gb=round(usage.used / (1024**3), 1),
        free_gb=round(usage.free / (1024**3), 1),
        usage_pct=round(usage.percent, 1),
    )


# --- Routes ---

@router.get("/gpu", response_model=GPUMetricsResponse)
async def get_gpu_metrics() -> GPUMetricsResponse:
    """Get real-time GPU metrics."""
    return _parse_gpu_info()


@router.get("/cpu", response_model=CPUMetricsResponse)
async def get_cpu_metrics() -> CPUMetricsResponse:
    """Get real-time CPU metrics."""
    return _parse_cpu_info()


@router.get("/ram", response_model=RAMMetricsResponse)
async def get_ram_metrics() -> RAMMetricsResponse:
    """Get real-time RAM metrics."""
    return _parse_ram_info()


@router.get("/disk", response_model=DiskMetricsResponse)
async def get_disk_metrics(path: str = "D:") -> DiskMetricsResponse:
    """Get disk usage for a given path."""
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"Path not found: {path}")
    return _parse_disk_info(path)


@router.get("/queue", response_model=QueueMetricsResponse)
async def get_queue_metrics() -> QueueMetricsResponse:
    """Get ComfyUI queue status."""
    try:
        from backend.comfyui_client import ComfyUIClient
        client = ComfyUIClient()
        status = client.get_queue_status()
        return QueueMetricsResponse(
            running=status.running,
            pending=status.pending,
        )
    except Exception:
        return QueueMetricsResponse()


@router.get("/overview", response_model=OverviewResponse)
async def get_overview() -> OverviewResponse:
    """Get complete system overview in one call."""
    from datetime import datetime

    gpu = _parse_gpu_info()
    cpu = _parse_cpu_info()
    ram = _parse_ram_info()
    disk = _parse_disk_info("D:")
    queue = QueueMetricsResponse()

    try:
        from backend.comfyui_client import ComfyUIClient
        client = ComfyUIClient()
        qs = client.get_queue_status()
        queue = QueueMetricsResponse(running=qs.running, pending=qs.pending)
    except Exception:
        pass

    is_ready = gpu.vram_free_mb > 2048 and gpu.is_idle and queue.running == 0

    return OverviewResponse(
        timestamp=datetime.now().isoformat(),
        gpu=gpu,
        cpu=cpu,
        ram=ram,
        disk=disk,
        queue=queue,
        is_ready=is_ready,
    )


# ----------------------------------------------------------
# Legacy / Common Hardware Info
# ----------------------------------------------------------

@router.get("/hardware")
async def get_hardware_info() -> Dict[str, Any]:
    """Get summarized hardware info (for web console display)."""
    gpu = _parse_gpu_info()
    cpu = _parse_cpu_info()
    ram = _parse_ram_info()
    disk = _parse_disk_info("D:")

    return {
        "gpu": {
            "name": gpu.name,
            "vram": f"{gpu.vram_used_mb}MB / {gpu.vram_total_mb}MB",
            "utilization": f"{gpu.utilization_pct}%",
            "temperature": f"{gpu.temperature_c}°C",
        },
        "cpu": {
            "model": cpu.model,
            "cores": f"{cpu.cores_physical}C/{cpu.cores_logical}T",
            "usage": f"{cpu.usage_pct}%",
        },
        "ram": {
            "total": f"{ram.total_gb}GB",
            "used": f"{ram.used_gb}GB",
            "usage": f"{ram.usage_pct}%",
        },
        "disk": {
            "path": disk.path,
            "free": f"{disk.free_gb}GB",
            "usage": f"{disk.usage_pct}%",
        },
    }
