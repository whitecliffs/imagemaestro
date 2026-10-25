"""Device and platform compatibility abstraction for Maestro.

Enables seamless execution on:
- Apple Silicon (macOS with Metal Performance Shaders / MPS)
- AMD GPUs (Linux with ROCm / HIP)
- NVIDIA GPUs (CUDA)
- CPU fallback

Provides mock/shim interfaces for CUDA-specific constructs (cudart, streams, events,
device capabilities, memory queries) when running on non-NVIDIA hardware, ensuring
the entire WanGP / MMGP pipeline runs reliably without crashing.
"""
from __future__ import annotations

import os
import sys
import platform
import types
from typing import Any, NamedTuple

try:
    import psutil
except ImportError:
    class MockVirtualMemory:
        total = 16 * 1024**3
        available = 8 * 1024**3

    class MockPsutil:
        @staticmethod
        def virtual_memory():
            return MockVirtualMemory()

    psutil = MockPsutil()  # type: ignore

try:
    import torch
except ImportError:
    torch = None  # type: ignore


class MockDeviceProperties:
    def __init__(self, name: str = "GPU", total_memory: int = 16 * 1024**3, major: int = 0, minor: int = 0):
        self.name = name
        self.total_memory = total_memory
        self.major = major
        self.minor = minor
        self.multi_processor_count = os.cpu_count() or 8
        self.gcnArchName = ""

    def __repr__(self):
        return f"_MockDeviceProperties(name='{self.name}', total_memory={self.total_memory // (1024**2)}MB, major={self.major}, minor={self.minor})"


class MockCudart:
    @staticmethod
    def cudaHostRegister(ptr: int, size: int, flags: int) -> int:
        return 0

    @staticmethod
    def cudaHostUnregister(ptr: int) -> int:
        return 0

    @staticmethod
    def cudaGetErrorString(error: int) -> str:
        return "Success"


class MockStream:
    def __init__(self, device: Any = None, priority: int = 0):
        self.device = device
        self.priority = priority

    def wait_stream(self, stream: Any) -> None:
        pass

    def wait_event(self, event: Any) -> None:
        pass

    def synchronize(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockEvent:
    def __init__(self, enable_timing: bool = False, blocking: bool = False, interprocess: bool = False):
        self._recorded = False

    def record(self, stream: Any = None) -> None:
        self._recorded = True

    def wait(self, stream: Any = None) -> None:
        pass

    def synchronize(self) -> None:
        pass

    def query(self) -> bool:
        return True

    def elapsed_time(self, end_event: Any) -> float:
        return 0.0


class StreamContext:
    def __init__(self, stream: Any):
        self.stream = stream

    def __enter__(self):
        return self.stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def get_default_device() -> str:
    """Determine best available computing device."""
    if torch is None:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() in ("arm64", "aarch64")


def is_rocm() -> bool:
    if torch is None:
        return False
    return bool(torch.cuda.is_available() and getattr(torch.version, "hip", None) is not None)


def is_mps_available() -> bool:
    if torch is None:
        return False
    return bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available())


def get_total_vram_bytes(device: Any = None) -> int:
    """Get total memory for the active acceleration device in bytes."""
    if torch is not None and torch.cuda.is_available():
        try:
            dev_idx = 0 if device is None else (device.index if hasattr(device, "index") and device.index is not None else 0)
            return torch.cuda.get_device_properties(dev_idx).total_memory
        except Exception:
            pass
    return psutil.virtual_memory().total


def get_available_vram_bytes(device: Any = None) -> int:
    """Get available memory in bytes."""
    if torch is not None and torch.cuda.is_available():
        try:
            free, _ = torch.cuda.mem_get_info(device)
            return free
        except Exception:
            pass
    return psutil.virtual_memory().available


def sync_device() -> None:
    """Synchronize the active accelerator."""
    if torch is None:
        return
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    elif is_mps_available() and hasattr(torch.mps, "synchronize"):
        torch.mps.synchronize()


def clear_device_cache() -> None:
    """Clear memory cache for the active device."""
    if torch is None:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    if is_mps_available() and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()


def setup_device_compatibility():
    """Apply monkey patches and wrappers to torch for seamless non-CUDA or ROCm execution."""
    if torch is None or getattr(torch, "_imagemaestro_compat_ready", False):
        return
    torch._imagemaestro_compat_ready = True
    default_dev = get_default_device()
    mps_active = is_mps_available()
    rocm_active = is_rocm()

    # 1. On ROCm, torch.cuda.cudart does not exist. Provide it.
    if rocm_active or not torch.cuda.is_available() or not hasattr(torch.cuda, "cudart"):
        torch.cuda.cudart = lambda: MockCudart()

    # 2. If CUDA is NOT available at all (e.g. macOS Apple Silicon or CPU)
    if not torch.cuda.is_available():
        print(f"[DeviceCompat] Initializing compatibility layer: Target device is '{default_dev}' (Apple Silicon / CPU)")

        # Provide device properties
        mem_bytes = psutil.virtual_memory().total
        dev_name = "Apple Silicon GPU (Metal / MPS)" if mps_active else "CPU"
        props = MockDeviceProperties(name=dev_name, total_memory=mem_bytes, major=0, minor=0)

        orig_get_device_properties = getattr(torch.cuda, "get_device_properties", None)
        torch.cuda.get_device_properties = lambda d=None: props

        orig_get_device_capability = getattr(torch.cuda, "get_device_capability", None)
        torch.cuda.get_device_capability = lambda d=None: (0, 0)

        torch.cuda.current_device = lambda: 0
        torch.cuda.device_count = lambda: 1 if mps_active else 0
        torch.cuda.get_device_name = lambda d=0: dev_name
        torch.cuda.set_device = lambda d: None
        torch.cuda.mem_get_info = lambda d=None: (psutil.virtual_memory().available, mem_bytes)

        if mps_active:
            torch.cuda.empty_cache = lambda: torch.mps.empty_cache() if hasattr(torch.mps, "empty_cache") else None
            torch.cuda.synchronize = lambda d=None: torch.mps.synchronize() if hasattr(torch.mps, "synchronize") else None
            torch.cuda.manual_seed = lambda s: torch.mps.manual_seed(s) if hasattr(torch.mps, "manual_seed") else torch.manual_seed(s)
            torch.cuda.manual_seed_all = lambda s: torch.mps.manual_seed(s) if hasattr(torch.mps, "manual_seed") else torch.manual_seed(s)
            if hasattr(torch.mps, "current_allocated_memory"):
                torch.cuda.memory_allocated = lambda d=None: torch.mps.current_allocated_memory()
                torch.cuda.memory_reserved = lambda d=None: torch.mps.current_allocated_memory()
            else:
                torch.cuda.memory_allocated = lambda d=None: 0
                torch.cuda.memory_reserved = lambda d=None: 0
        else:
            torch.cuda.empty_cache = lambda: None
            torch.cuda.synchronize = lambda d=None: None
            torch.cuda.manual_seed = lambda s: None
            torch.cuda.manual_seed_all = lambda s: None
            torch.cuda.memory_allocated = lambda d=None: 0
            torch.cuda.memory_reserved = lambda d=None: 0

        torch.cuda.Stream = MockStream
        torch.cuda.Event = MockEvent
        torch.cuda.current_stream = lambda d=None: MockStream()
        torch.cuda.default_stream = lambda d=None: MockStream()
        torch.cuda.stream = lambda s: StreamContext(s)

        # Patch Tensor.cuda and nn.Module.cuda to route to default_dev
        def _tensor_cuda(self, device=None, non_blocking=False, **kwargs):
            target = default_dev
            if device is not None and str(device) not in ("cuda", "cuda:0", "0"):
                target = device
            return self.to(target, non_blocking=(non_blocking and target != "cpu"), **kwargs)

        def _module_cuda(self, device=None):
            target = default_dev
            if device is not None and str(device) not in ("cuda", "cuda:0", "0"):
                target = device
            return self.to(target)

        torch.Tensor.cuda = _tensor_cuda
        torch.nn.Module.cuda = _module_cuda
    else:
        # CUDA is available (either NVIDIA or ROCm)
        # Ensure get_device_capability does not throw on ROCm
        if rocm_active:
            print(f"[DeviceCompat] Initializing compatibility layer: Target device is AMD ROCm/HIP ({torch.cuda.get_device_name(0)})")
            orig_cap = torch.cuda.get_device_capability
            def _safe_cap(dev=None):
                try:
                    return orig_cap(dev)
                except Exception:
                    return (0, 0)
            torch.cuda.get_device_capability = _safe_cap
