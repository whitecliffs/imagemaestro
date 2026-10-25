# AMD GPU (Linux & ROCm) Setup & Optimization Guide

This guide covers running **ImageMaestro** on AMD Radeon and AMD Instinct GPUs under Linux using **ROCm / HIP**.

---

## 🔴 Supported Hardware

- **AMD RDNA3 / RDNA3.5**: Radeon RX 7900 XTX, 7900 XT, 7800 XT, 7700 XT, 7600, Radeon 780M / 890M integrated graphics.
- **AMD RDNA2**: Radeon RX 6950 XT, 6900 XT, 6800 XT, 6800, 6700 XT.
- **AMD RDNA4**: Next-gen Radeon RX 9000 series.
- **AMD CDNA**: Instinct MI100, MI200, MI300 series.

---

## 🐧 Prerequisites

### 1. User Permissions for AMD Render Nodes
Ensure your user account belongs to the `render` and `video` groups to access `/dev/kfd` and `/dev/dri/renderD128`:
```bash
sudo usermod -a -G render,video $USER
```
*(Log out and log back in for group changes to take effect).*

### 2. Verify Kernel ROCm Driver
Check that the kernel module is active:
```bash
ls -la /dev/kfd
```
If `/dev/kfd` exists, your kernel has AMD KFD driver support enabled.

---

## ⚡ Quick Installation

1. Navigate to the ImageMaestro project directory:
   ```bash
   cd /home/jim/projects/imagemaestro
   ```

2. Run the installer:
   ```bash
   ./install.sh
   ```
   *The installer automatically detects your AMD GPU and installs PyTorch with ROCm 6.4 wheels along with `requirements-rocm.txt`.*

3. Start ImageMaestro:
   ```bash
   ./start.sh
   ```

---

## 🎯 AMD RDNA3 / Integrated GPU Optimization (e.g. 780M)

On consumer AMD GPUs (like the Radeon 780M HawkPoint or RX 7000 series), ROCm occasionally requires an architecture override if your specific model ID is not in the default upstream list.

If PyTorch warns that your GPU architecture is unlisted or ROCm fails to initialize:
```bash
# For RDNA3 (RX 7000 series, 780M, 890M):
export HSA_OVERRIDE_GFX_VERSION=11.0.0

# For RDNA2 (RX 6000 series):
export HSA_OVERRIDE_GFX_VERSION=10.3.0
```
Then launch ImageMaestro:
```bash
./start.sh
```

---

## 🧠 Recommended AMD Settings

### VRAM Profiles:
- **Integrated GPU / 8 GB VRAM**:
  - Video Profile: `4.5` (conserves VRAM, streams layers from system RAM)
  - Transformer Quantization: `INT8`
  - VAE Tiling Config: `3` (Aggressive tiling)
- **12 GB – 16 GB VRAM** (e.g. RX 7800 XT, 6800 XT):
  - Video Profile: `3.5` or `3.0`
  - Transformer Quantization: `FP16` or `BF16`
  - VAE Tiling Config: `2` (Medium)
- **24 GB VRAM** (e.g. RX 7900 XTX):
  - Video Profile: `2.0` or `1.0`
  - Transformer Quantization: `BF16`
  - VAE Tiling Config: `1` (Full / Auto)

### Attention Mode:
Always select **`sdpa`** (PyTorch native Scaled Dot-Product Attention).
ROCm compiles SDPA with MIOpen and rocBLAS, delivering optimal throughput on AMD hardware without needing proprietary CUDA libraries.

---

## 🔧 Useful Commands

```bash
# Force AMD GPU
./start.sh --gpu cuda

# Run with custom port
./start.sh --port 7860

# Allow remote access over local network
./start.sh --listen
```
