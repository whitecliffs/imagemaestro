#!/usr/bin/env python3
"""ImageMaestro Standalone Installer
No Pinokio required. Supports macOS (Apple Silicon), AMD Linux (ROCm), NVIDIA, and CPU.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
APP_DIR = ROOT_DIR / "app"
UI_DIR = ROOT_DIR / "ui"
VENV_DIR = ROOT_DIR / "venv"


def print_banner():
    print("""
============================================================
              ImageMaestro Standalone Installer
         100% Local AI Creative Studio & Director
       Standalone Edition (Apple Silicon, AMD, NVIDIA)
============================================================
""")


def detect_system() -> dict[str, str | bool]:
    sys_name = sys.platform
    machine = platform.machine().lower()
    is_mac = sys_name == "darwin"
    is_arm = machine in ("arm64", "aarch64")
    is_apple_silicon = is_mac and is_arm

    gpu_type = "cpu"
    gpu_desc = "CPU Fallback"

    if is_apple_silicon:
        gpu_type = "apple_silicon"
        gpu_desc = f"Apple Silicon ({machine})"
    elif sys_name == "linux":
        # Check for AMD GPU
        has_rocm_dev = os.path.exists("/dev/kfd")
        has_amd_lspci = False
        has_nvidia_lspci = False

        if shutil.which("lspci"):
            try:
                lspci_out = subprocess.check_output(["lspci"], text=True, stderr=subprocess.DEVNULL).lower()
                gpu_lines = [line for line in lspci_out.splitlines() if any(kind in line for kind in ("vga compatible", "3d controller", "display controller"))]
                if any(any(x in line for x in ("amd", "radeon", "advanced micro devices")) for line in gpu_lines):
                    has_amd_lspci = True
                if any("nvidia" in line for line in gpu_lines):
                    has_nvidia_lspci = True
            except Exception:
                pass

        if shutil.which("nvidia-smi") or has_nvidia_lspci:
            gpu_type = "nvidia"
            gpu_desc = "NVIDIA CUDA GPU"
        elif has_rocm_dev or has_amd_lspci:
            gpu_type = "amd_rocm"
            gpu_desc = "AMD Radeon GPU (ROCm/HIP)"
    elif sys_name == "win32":
        if shutil.which("nvidia-smi"):
            gpu_type = "nvidia"
            gpu_desc = "NVIDIA CUDA GPU"

    return {
        "os": sys_name,
        "machine": machine,
        "is_mac": is_mac,
        "is_apple_silicon": is_apple_silicon,
        "gpu_type": gpu_type,
        "gpu_desc": gpu_desc,
    }


def find_python() -> str:
    """Find a suitable Python binary (preferably 3.10, 3.11, or 3.12)."""
    if sys.version_info[:2] == (3, 11):
        return sys.executable
    path = shutil.which("python3.11")
    if path:
        return path
    raise RuntimeError("Python 3.11 is required. Use the packaged installer to provision it automatically.")


def create_virtualenv(python_bin: str, venv_path: Path) -> Path:
    """Create a virtual environment if one does not already exist."""
    pip_bin = venv_path / ("bin" if sys.platform != "win32" else "Scripts") / "pip"
    py_bin = venv_path / ("bin" if sys.platform != "win32" else "Scripts") / ("python" if sys.platform != "win32" else "python.exe")

    if not venv_path.exists() or not py_bin.exists():
        print(f"[*] Creating virtual environment in {venv_path} using {python_bin}...")
        # Check if uv is available
        if shutil.which("uv"):
            print("  Using fast 'uv venv'...")
            subprocess.check_call(["uv", "venv", "--seed", "--python", python_bin, str(venv_path)])
        else:
            subprocess.check_call([python_bin, "-m", "venv", str(venv_path)])

    # Upgrade pip and setuptools
    print("[*] Ensuring pip and setuptools are up to date...")
    try:
        subprocess.check_call([str(py_bin), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    except subprocess.CalledProcessError:
        print("[!] Warning: Could not upgrade pip. Continuing with installed version.")

    return py_bin


def install_pytorch(py_bin: Path, gpu_type: str):
    """Install the correct PyTorch build for the target hardware."""
    print(f"\n[*] Installing PyTorch for target hardware: {gpu_type.upper()}...")

    if gpu_type == "apple_silicon":
        print("  Installing official PyTorch with Apple Silicon Metal Performance Shaders (MPS)...")
        cmd = [str(py_bin), "-m", "pip", "install", "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1"]
    elif gpu_type == "amd_rocm":
        print("  Installing PyTorch with AMD ROCm acceleration...")
        cmd = [
            str(py_bin), "-m", "pip", "install",
            "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1",
            "--index-url", "https://download.pytorch.org/whl/rocm6.4"
        ]
    elif gpu_type == "nvidia":
        print("  Installing PyTorch with NVIDIA CUDA acceleration...")
        cmd = [
            str(py_bin), "-m", "pip", "install",
            "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1",
            "--index-url", "https://download.pytorch.org/whl/cu128"
        ]
    else:
        print("  Installing standard CPU PyTorch...")
        cmd = [
            str(py_bin), "-m", "pip", "install",
            "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1",
            "--index-url", "https://download.pytorch.org/whl/cpu"
        ]

    subprocess.check_call(cmd)
    if gpu_type == "amd_rocm":
        probe = "import torch; assert torch.version.hip and torch.cuda.is_available(), 'ROCm cannot access an AMD GPU'; arch = torch.cuda.get_device_properties(0).gcnArchName.split(':')[0]; assert arch in torch.cuda.get_arch_list(), f'GPU {arch} is not supported by this PyTorch wheel; no architecture override has been applied'"
        subprocess.check_call([str(py_bin), "-c", probe])
    elif gpu_type == "apple_silicon":
        subprocess.check_call([str(py_bin), "-c", "import torch; assert torch.backends.mps.is_available(), 'PyTorch Metal acceleration is unavailable'"])


def install_dependencies(py_bin: Path, gpu_type: str):
    """Install required Python dependencies."""
    print("\n[*] Installing application dependencies...")
    req_file = ROOT_DIR / "requirements.txt"
    if gpu_type == "apple_silicon":
        req_file = ROOT_DIR / "requirements-macos.txt"
    elif gpu_type == "amd_rocm":
        req_file = ROOT_DIR / "requirements-rocm.txt"
    elif gpu_type == "nvidia":
        req_file = ROOT_DIR / "requirements-cuda.txt"

    print(f"  Reading package list from {req_file.name}...")
    subprocess.check_call([str(py_bin), "-m", "pip", "install", "-c", str(ROOT_DIR / "constraints.txt"), "-r", str(req_file)])


def check_and_build_ui():
    """Ensure the web UI is built and ready."""
    dist_html = UI_DIR / "dist" / "index.html"
    if dist_html.is_file():
        print("[*] Web UI is already compiled and ready in ui/dist/.")
        return

    print("\n[*] Web UI not built yet. Checking for Node.js and npm...")
    if shutil.which("npm"):
        print("  Building Web UI with npm...")
        subprocess.check_call(["npm", "ci"], cwd=str(UI_DIR))
        subprocess.check_call(["npm", "run", "build"], cwd=str(UI_DIR))
        print("  Web UI built successfully!")
    else:
        print("[!] Note: npm not found. Gradio classic UI (/classic) and API will be available.")
        print("    To enable the modern Studio UI, install Node.js and run: cd ui && npm install && npm run build")


def main():
    if "--cloud-only" in sys.argv:
        subprocess.check_call([sys.executable, str(ROOT_DIR / "packaging/desktop.py"), str(ROOT_DIR), "--cloud-only"])
        print("Cloud launcher installed. Run python3 cloud_launcher.py or open ImageMaestro Cloud from your applications.")
        return
    print_banner()
    parser = argparse.ArgumentParser(description="ImageMaestro Standalone Installer")
    parser.add_argument("--gpu", choices=["auto", "apple_silicon", "amd_rocm", "nvidia", "cpu"], default="auto",
                        help="Target GPU hardware (default: auto-detect)")
    parser.add_argument("--venv", default=str(VENV_DIR), help="Virtualenv directory path")
    parser.add_argument("--skip-torch", action="store_true", help="Skip PyTorch installation")
    parser.add_argument("--skip-ui", action="store_true", help="Skip UI build step")
    args = parser.parse_args()

    hw = detect_system()
    selected_gpu = hw["gpu_type"] if args.gpu == "auto" else args.gpu

    print("Detected Environment:")
    print(f"  • Operating System: {hw['os']} ({hw['machine']})")
    print(f"  • Hardware Profile: {hw['gpu_desc']}")
    print(f"  • Selected Target:  {selected_gpu.upper()}")
    print(f"  • Project Directory: {ROOT_DIR}")
    print()

    python_bin = find_python()
    venv_path = Path(args.venv).resolve()
    py_bin = create_virtualenv(python_bin, venv_path)

    if not args.skip_torch:
        install_pytorch(py_bin, selected_gpu)

    install_dependencies(py_bin, selected_gpu)

    check = subprocess.run([str(py_bin), "-m", "pip", "check"], capture_output=True, text=True)
    # PyPI's decord 0.6.0 py3 wheel embeds an incorrect cp36 WHEEL tag.
    # Validate its actual native import, and retain failure for all other conflicts.
    issues = [line for line in check.stdout.splitlines() if line.strip()]
    known_decord_tag = "decord 0.6.0 is not supported on this platform"
    if known_decord_tag in issues:
        subprocess.check_call([str(py_bin), "-c", "import decord; print('Decord native import: OK')"])
        print("Warning: decord 0.6.0 has an upstream wheel-tag defect; native import verified.")
        issues.remove(known_decord_tag)
    if check.returncode and (issues or check.stderr.strip()):
        raise RuntimeError("Dependency validation failed: " + "\n".join(issues) + check.stderr)
    if not args.skip_ui:
        check_and_build_ui()
    subprocess.check_call([str(py_bin), "-c", "import torch, gradio, fastapi; from shared.device_compat import setup_device_compatibility; setup_device_compatibility(); torch.manual_seed(1); print('Runtime imports and random seed: OK')"], cwd=str(APP_DIR))
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} is required. Install FFmpeg and run the installer again.")

    print("""
============================================================
              Installation Complete!
============================================================
To launch ImageMaestro:
  ./start.sh
or:
  python3 run.py

Web UI will be available at:
  • Modern Studio UI:  http://127.0.0.1:7860/
  • Classic Gradio UI: http://127.0.0.1:7860/classic/
  • REST API Docs:     http://127.0.0.1:7860/docs
============================================================
""")


if __name__ == "__main__":
    main()
