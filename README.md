# ImageMaestro

**Standalone, Pinokio-Free AI Creative Studio & Director**  
*Optimized for Apple Silicon (macOS) & AMD GPUs (Linux / ROCm), with full NVIDIA & CPU support.*

> **Preview status:** Linux CPU server startup has been tested. Full Apple Silicon,
> ROCm and CPU generation support is not yet certified; some pipelines still require
> CUDA. Read [the security and portability review](docs/STANDALONE_REVIEW.md) before
> enabling LAN access or distributing this build.

Prebuilt online installers are in `dist-installers/`: run the Linux x86_64 `.run`
with Bash, or unzip and open the macOS Apple Silicon `.command`. They install
private Python/FFmpeg runtimes and add a desktop launcher without root access.
Internet access is required; model weights download separately. Mac installers
are unsigned and may require explicit Gatekeeper approval.

---

## 🌟 Overview

**ImageMaestro** is an independent, standalone distribution of [Blizaine/Maestro](https://github.com/Blizaine/Maestro) engineered to run completely free of [Pinokio](https://pinokio.computer/) and fully supporting **Apple Silicon (macOS)** and **AMD GPUs (Linux)**.

Upstream Maestro was strictly gated to Windows/Linux NVIDIA systems via Pinokio scripts (`gpu !== 'nvidia'`), hardcoded CUDA runtime calls (`torch.cuda.cudart()`), NVIDIA-only compute capabilities (`torch.cuda.get_device_capability()`), and proprietary CUDA wheels (`cu130`, `lightx2v`, `nunchaku`, `sageattention`).

**ImageMaestro** resolves these limitations through:
1. **Zero Pinokio Dependency**: Clean standalone CLI installers and launchers (`install.sh`, `start.sh`, `install.py`, `run.py`).
2. **Native Apple Silicon (MPS)**: Metal Performance Shaders acceleration leveraging Apple Unified Memory on M1/M2/M3/M4 Macs.
3. **Native AMD GPU (ROCm/HIP)**: Full hardware acceleration for AMD Radeon / Instinct GPUs on Linux.
4. **Universal SDPA Attention**: Scaled Dot-Product Attention (`F.scaled_dot_product_attention`) enabled across all platforms without requiring NVIDIA-proprietary CUDA kernels.
5. **Cross-Platform Device Compatibility Layer**: `shared.device_compat` transparently translates CUDA-specific calls (streams, events, memory queries, offloading) on non-CUDA systems.
6. **Pre-Built Modern Studio UI**: React 19 + TailwindCSS Vite bundle compiled in `ui/dist/` and served directly by FastAPI.

---

## Cloud GPU preview

Open **Cloud GPU** in the local Studio, or run `python3 cloud_launcher.py` directly.
Cloud control does not load local models or require a local GPU. Connect your own
Runpod account to see live NVIDIA prices, start a private browser studio, download
outputs, and stop the rented GPU. The signup link supports ImageMaestro through
Runpod's referral programme.

Use `--cloud-only` with the standalone installer to skip local AI dependencies.
See [cloud setup, billing safeguards and publishing](docs/RUNPOD_CLOUD.md).
A tested published container image must be configured before paid launch is enabled.

## 🚀 Quick Start

### 1. Installation

Clone or enter the project directory:
```bash
cd /home/jim/projects/imagemaestro
```

Run the standalone installer:
```bash
./install.sh
```
*Or using Python:*
```bash
python3 install.py
```

The installer automatically:
- Detects your operating system and GPU hardware (Apple Silicon, AMD ROCm, NVIDIA, or CPU).
- Sets up an isolated Python virtual environment in `venv/`.
- Installs the correct PyTorch build (MPS for macOS, ROCm 6.4 for AMD, CUDA for NVIDIA, or CPU).
- Installs required dependencies without incompatible CUDA-only packages.
- Verifies the compiled Web UI in `ui/dist/`.

### 2. Launching ImageMaestro

Start the server:
```bash
./start.sh
```
*Or using Python:*
```bash
python3 run.py
```

Once running, access ImageMaestro in your browser:
- **Modern Studio UI**: [http://127.0.0.1:7860/](http://127.0.0.1:7860/)
- **Classic Gradio UI**: [http://127.0.0.1:7860/classic/](http://127.0.0.1:7860/classic/)
- **Interactive REST API Docs**: [http://127.0.0.1:7860/docs](http://127.0.0.1:7860/docs)

---

## 💻 Hardware Support Matrix

| Hardware Platform | Backend | Attention Backend | Transformer Quantization | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Apple Silicon Mac** (M1/M2/M3/M4) | MPS (Metal) | PyTorch SDPA | BF16 / FP16 | ✅ Supported |
| **AMD Radeon / Instinct** (Linux) | ROCm / HIP | PyTorch SDPA | BF16 / FP16 / INT8 | ✅ Supported |
| **NVIDIA GeForce / RTX** | CUDA | SDPA / Flash / Sage | BF16 / FP16 / INT8 / FP8 | ✅ Supported |
| **CPU Fallback** (Any OS) | CPU | PyTorch SDPA | INT8 / FP32 | ✅ Supported |

---

## ⚙️ Launcher Options & Customization

The standalone runner `run.py` accepts convenient command-line flags:

```bash
# Force a specific device (mps, cuda, cpu)
./start.sh --gpu mps
./start.sh --gpu cuda
./start.sh --gpu cpu

# Bind to custom port or allow LAN access
./start.sh --port 8080
./start.sh --listen          # Binds to 0.0.0.0 for access over local network

# Disable auto-opening browser
./start.sh --no-browser

# Enable PyTorch 2.x compilation
./start.sh --compile
```

---

## 🛠️ Architecture & Decompilation Analysis

Upstream Maestro was tightly bundled with Pinokio's JSON/JS script runner. Below is a breakdown of why upstream failed on non-NVIDIA systems and how ImageMaestro solves it:

### 1. Pinokio Install Gatekeeping
- **Upstream Problem**: `install.js` contained `when: "{{gpu !== 'nvidia'}}"` with the hard exit message: *"This app requires an NVIDIA GPU on Windows or Linux."* `torch.js` had explicit checks throwing `Error("Maestro's NVIDIA runtime is supported on Windows and Linux.")`.
- **Solution**: Removed Pinokio script dependency entirely. Created native `install.py` / `install.sh` that detects Darwin/macOS arm64 and Linux AMD GPUs, routing to appropriate PyTorch distributions.

### 2. Device Initialization Crashes
- **Upstream Problem**: In `app/wgp.py` line 2643:
  ```python
  gpu_major, gpu_minor = torch.cuda.get_device_capability(args.gpu if len(args.gpu) > 0 else None)
  ```
  On Apple Silicon or CPU, `torch.cuda.is_available()` is `False`. Calling `get_device_capability()` causes immediate fatal crash: `AssertionError: Torch not compiled with CUDA enabled`.
- **Solution**: Implemented `shared.device_compat` which patches `torch.cuda` with safe mock properties and capability queries (`(0, 0)`), dynamically selecting `mps`, `cuda`, or `cpu`.

### 3. Missing CUDA Runtime (`cudart`) on AMD & macOS
- **Upstream Problem**: `app/mmgp/offload.py` makes direct calls to NVIDIA's CUDA Runtime library:
  ```python
  torch.cuda.cudart().cudaHostRegister(self.pointer, self.size, 0)
  ```
  On AMD ROCm, PyTorch maps `torch.cuda` to HIP, but `cudart` does not exist (raising `AttributeError`). On macOS, CUDA does not exist at all.
- **Solution**: Guarded host registration and provided `MockCudart` in `device_compat.py`. On non-NVIDIA hardware, host memory locking is cleanly bypassed with zero overhead, allowing MMGP offloading to operate safely in system RAM.

### 4. Direct `.cuda()` Method Calls
- **Upstream Problem**: Hundreds of modules across `app/models/`, `app/preprocessing/`, and `app/postprocessing/` call `.cuda()` directly on tensors and `nn.Module` objects without checking device availability.
- **Solution**: `device_compat.py` monkey-patches `torch.Tensor.cuda` and `torch.nn.Module.cuda` when CUDA is unavailable, transparently redirecting them to the active accelerator (`mps` or `cpu`).

### 5. Memory Capacity and Unified Memory
- **Upstream Problem**: VRAM capacity checks called `torch.cuda.get_device_properties(0).total_memory`. On Apple Silicon, GPU memory is shared unified memory.
- **Solution**: On macOS, memory queries read total system memory via `psutil.virtual_memory().total`, giving accurate capacity calculations to WanGP VAE tiling, model splitting, and offload budgets.

---

## 📁 Repository Layout

```
imagemaestro/
├── app/                        # Python backend application
│   ├── launch.py               # FastAPI server (modern UI + API + Gradio mount)
│   ├── wgp.py                  # Core WanGP engine & model pipelines
│   ├── mmgp/                   # Memory Management for the GPU Poor (offloader)
│   ├── shared/
│   │   ├── device_compat.py    # Cross-platform device & PyTorch compatibility shim
│   │   ├── attention.py        # Attention router (SDPA, Sage, Flash)
│   │   └── cuda_memory.py      # Early allocator selection
│   ├── services/
│   │   ├── hardware_detect.py  # Hardware probing (Apple Silicon, AMD, NVIDIA, RAM)
│   │   └── perf_recommend.py   # Performance auto-tune recommendation engine
│   └── postprocessing/seedvc/  # Seed-VC voice conversion submodule
├── ui/                         # React 19 + TypeScript + Vite UI source
│   ├── dist/                   # Compiled production Web UI bundle
│   └── package.json            # Frontend package definitions
├── docs/                       # Platform-specific guides
│   ├── MACOS_APPLE_SILICON.md  # Detailed Mac Mini / Apple Silicon guide
│   └── AMD_LINUX_ROCM.md       # Detailed AMD Linux & ROCm guide
├── install.py                  # Standalone Python installer
├── install.sh                  # One-click Shell installer
├── run.py                      # Standalone Python runner
├── start.sh                    # One-click Shell launcher
├── build_ui.sh                 # Rebuilds the React frontend UI
├── requirements.txt            # Unified smart requirements
├── requirements-base.txt       # Core platform-neutral requirements
├── requirements-macos.txt      # Apple Silicon specific requirements
├── requirements-rocm.txt       # AMD ROCm specific requirements
└── requirements-cuda.txt       # NVIDIA CUDA specific requirements
```

---

## 📖 Platform Guides

- [Apple Silicon (macOS) Setup Guide](docs/MACOS_APPLE_SILICON.md)
- [AMD ROCm (Linux) Setup Guide](docs/AMD_LINUX_ROCM.md)

---

## 📄 License & Credits

- Based on **Maestro** by Blizaine & **WanGP** by DeepBeepMeep (WanGP Community License 2.0).
- Standalone multi-platform architecture and cross-platform patches developed for **ImageMaestro**.
