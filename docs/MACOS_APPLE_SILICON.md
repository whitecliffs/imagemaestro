# Apple Silicon (macOS) Setup & Optimization Guide

This guide covers running **ImageMaestro** on Apple Silicon Macs (Mac mini, MacBook Air/Pro, Mac Studio, Mac Pro with M1, M2, M3, or M4 chips).

---

## 🍎 Prerequisites

1. **macOS 13.0 (Ventura) or newer** (macOS 14 Sonoma or macOS 15 Sequoia recommended).
2. **Homebrew** (if not already installed):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
3. **Python 3.10, 3.11, or 3.12**:
   ```bash
   brew install python@3.11 ffmpeg
   ```

---

## ⚡ Quick Installation

1. Open **Terminal** and navigate to your ImageMaestro directory:
   ```bash
   cd /path/to/imagemaestro
   ```

2. Run the installer:
   ```bash
   ./install.sh
   ```
   *The installer detects Apple Silicon (arm64), installs official PyTorch with Metal Performance Shaders (MPS), and configures dependencies from `requirements-macos.txt`.*

3. Start ImageMaestro:
   ```bash
   ./start.sh
   ```

4. The browser will open to:
   - Modern Studio UI: `http://127.0.0.1:7860/`
   - Classic Gradio UI: `http://127.0.0.1:7860/classic/`

---

## 🧠 Memory & Performance Tuning on Apple Silicon

Apple Silicon features high-bandwidth **Unified Memory** shared between the CPU and the Metal GPU cores. ImageMaestro leverages this unified architecture to run large models that would normally exceed dedicated VRAM on standard consumer GPUs.

### Recommended Profiles by Unified Memory Size:

| Mac Model / RAM | Recommended Video Profile | Transformer Quantization | VAE Tiling Config |
| :--- | :--- | :--- | :--- |
| **8 GB RAM** | Profile 4.5 (Aggressive Offload) | INT8 | Aggressive (3) |
| **16 GB RAM** (e.g. Base Mac mini) | Profile 4.0 / 3.5 | FP16 / INT8 | Medium (2) |
| **24 GB – 36 GB RAM** | Profile 3.0 | BF16 / FP16 | Medium (2) |
| **64 GB – 128 GB+ RAM** (Mac Studio/Pro) | Profile 2.0 / 1.0 (High VRAM) | BF16 | Full / Auto (0) |

### Recommended Settings in the UI:
- **Attention Mode**: Set to `sdpa` (uses Apple Metal accelerated Scaled Dot-Product Attention).
- **Quantization**: `FP16` or `BF16` (Apple M-series chips have native hardware acceleration for FP16 and BF16 matrix multiplication).
- **VRAM Safety Coefficient**: `0.75` (leaves enough unified RAM for macOS system tasks and display server).

---

## 🔧 Useful CLI Flags on macOS

```bash
# Force MPS device explicitly
./start.sh --gpu mps

# Run purely on CPU (if testing or comparing performance)
./start.sh --gpu cpu

# Run on a different port if 7860 is used
./start.sh --port 7880

# Share across your local network so other devices can access it
./start.sh --listen
```

---

## ❓ Troubleshooting on macOS

### 1. `ImportError: cannot import name '...'`
Ensure you are using the virtual environment created by the installer:
```bash
source venv/bin/activate
pip install -r requirements-macos.txt
```

### 2. Metal Memory Limits
If macOS reports memory warnings during very large video rendering, you can instruct macOS to allocate more unified memory to PyTorch by setting:
```bash
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.85
./start.sh
```

### 3. Audio & Voice Conversion (SeedVC)
Voice conversion (Seed-VC) requires `ffmpeg`. Ensure ffmpeg is installed via Homebrew:
```bash
brew install ffmpeg
```
