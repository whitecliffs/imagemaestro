# Standalone security and portability review — 25 October 2026

Scope: targeted inspection of the installer, launcher, API boundary, device compatibility and model loading, plus a Linux CPU startup test. This is not a full security audit or validation of all 220 advertised model pipelines.

## Findings

1. **High: LAN access has no authentication.** `app/launch.py` explicitly describes its API as unauthenticated. `run.py --listen` exposes settings changes, uploads, model downloads and generation to any client that can reach the port. CORS only limits browser response access; it is not authentication. Keep the default loopback binding. The launcher now prints a warning for non-loopback binds. Authentication and authorization remain release work if network access is a supported product feature.
2. **High: the original loopback API lacked browser-origin/Host enforcement.** Restrictive CORS alone does not reject simple cross-origin requests or DNS-rebinding requests. Added ASGI middleware that rejects foreign browser origins (including `null`), unexpected Host names on loopback, and foreign-origin WebSockets. Same-origin UI access and origin-less local clients continue to work. This is browser isolation, not client authentication; other local processes can still access the server.
3. **High, conditional: model files can contain executable Python.** Examples include `weights_only=False` in `app/models/wan/alpha/utils.py:20` and `app/models/wan/scail/nlf/eager.py`, and `trust_remote_code=True` in `app/models/z_image/z_image_main.py` and other model loaders. Malicious pickle checkpoints or model repositories may execute code with the user's permissions when those paths are exercised. Treat model repositories and weights as trusted software. Some paths already verify hashes, such as `app/services/scail2_lora.py`; no blanket replacement was made because compatibility and provenance need per-loader review.
4. **Release blocker: full Apple Silicon/CPU generation support is not established.** `app/mmgp/offload.py` still contains hardcoded `.to("cuda")`, `torch.device("cuda")`, CUDA pinned allocation and an execution-device default of `cuda`. The shim redirects `.cuda()` methods but does not rewrite these paths. `ScailPoseProcessor` explicitly requires CUDA. A minimal CPU `offload.all` test on a two-input linear layer reproduced `AssertionError: Torch not compiled with CUDA enabled`. Server startup passing does not establish image/video generation support. ROCm maps CUDA APIs to HIP, but GPU/kernel compatibility still needs hardware testing. README support claims should not be treated as tested guarantees.
5. **Fixed installer errors.** Python selection accepted 3.13/3.14 despite older dependencies; uv omitted the chosen interpreter and pip seeding; AMD detection matched CPU/chipset entries; required `smplfitter` was missing; unconstrained Gradio could select version 6 despite use of the Gradio 5 API. The installer now uses Python 3.11, seeded environments, display-controller detection, dependency constraints, native-import validation and a pinned matching PyTorch/vision/audio set. ROCm uses the officially published 2.9.1 / 0.24.1 / 2.9.1 ROCm 6.4 wheel set: https://pytorch.org/get-started/previous-versions/ . This does not imply every AMD GPU supports ROCm 6.4.
6. **Fixed runtime errors.** CPU `torch.cuda.manual_seed_all` called `torch.manual_seed`, which calls it back recursively. CPU seed hooks now do nothing and setup is idempotent. CPU cudart now receives the intended mock. Launcher `--profile`/`--verbose` values are forwarded through `launch.py`.
7. **Mac media dependency blocker addressed for startup.** Removed unused unconditional decord import from shared media utilities, excluded decord from macOS requirements, and used the existing FFmpeg decoder when the primary video reader cannot import decord. Other optional model paths still use decord and require separate validation.
8. **Supply chain/reproducibility limitation.** Most Python dependencies retain broad version ranges; the installer is not fully locked or offline. Bundled micromamba is pinned at 2.8.1; installer payloads and bootstrap binaries have SHA-256 checksums. Conda/Python packages are fetched over HTTPS from their configured repositories. The self-extractor checksum detects accidental payload corruption; it is not a signature and does not authenticate a hostile replacement installer.
9. **Upstream decord packaging defect.** The 0.6.0 Linux wheel is named `py3-none-manylinux2010_x86_64` but embeds a CPython 3.6 WHEEL tag. pip reports it unsupported even though the ctypes-based native import succeeds on the tested Python 3.11 Linux runtime. Installer validation permits only that exact diagnostic after verifying native import; all other dependency conflicts fail installation.

## Dependency advisory scan

The initial backend environment scan reported **116 advisory records across 8
packages** (some records are duplicate aliases; this is not 116 proven exploitable
application bugs). The affected versions are:

| Package | Installed version | Advisory records |
| --- | --- | --- |
| accelerate | 1.12.0 | 1 |
| diffusers | 0.36.0 | 5 |
| filelock | 3.32.3 | 3 |
| gradio | 5.50.0 | 13 |
| pillow | 11.3.0 | 71 |
| rembg | 2.0.69 | 3 |
| starlette | 0.52.1 | 10 |
| transformers | 4.57.1 | 10 |

Examples include a Diffusers remote-code trust bypass, image parser memory-safety
issues in Pillow, and Gradio/Starlette request and file-handling issues. Some
advisories require features/platforms not used here. Upgrading everything to the
listed fixed versions would require major-version migrations (Gradio 6,
Transformers 5, Starlette 1) and pipeline regression testing, beyond a safe packaging
patch. **Do not treat these installers as security-cleared production releases.**

The frontend production scan initially reported a high-severity DOMPurify advisory
group. Updated DOMPurify to 3.4.17 and rebuilt the bundled UI; the repeated production
scan reported zero known advisories. Development-tool dependencies were excluded
from this production result.

## Installer output

`packaging/build.py` creates a Linux x86_64 `.run` and an Apple Silicon macOS `.command` (also zipped), plus checksums. Each contains project source, compiled React assets and the target micromamba binary. Python 3.11 and FFmpeg are provisioned into a private runtime; Python packages go in a separate virtual environment. No root access or system package changes are required. Existing installation directories are never overwritten automatically.

Linux default install location: `$XDG_DATA_HOME/ImageMaestro`, or `~/.local/share/ImageMaestro`; application-menu launcher: `applications/imagemaestro.desktop` under the same data directory. Mac default: `~/Library/Application Support/ImageMaestro`, with a launcher in `~/Applications/ImageMaestro.app`. Set `IMAGEMAESTRO_INSTALL_DIR` to change the installation location. Rerun `packaging/bootstrap/install.command` inside an existing installation to retry a failed install. First generation downloads additional model weights.

The AMD installer now rejects unavailable HIP devices and GPU architectures missing from the selected PyTorch wheel before installing the rest of the application. It does not silently apply `HSA_OVERRIDE_GFX_VERSION`.

The macOS installer and generated application are unsigned and unnotarized; Gatekeeper may require the user to explicitly allow them. A signed, notarized DMG/PKG requires Apple signing credentials and a macOS build/signing host. The Linux `.run` can be launched from a terminal with `bash ImageMaestro-3.2.5-linux-x86_64.run`; file-manager double-click behavior depends on executable-script policy. These are initial test installers, not certified production releases.

## Validation

- Six focused setup/security tests passed.
- TypeScript and Vite production build passed (existing large-chunk warning).
- Linux private Python 3.11 + FFmpeg micromamba runtime created successfully.
- Full generated Linux installer completed in `/home/jim/Work/imagemaestro-install-test`, including private Python/FFmpeg, dependencies and desktop launcher. The generated launcher started successfully; UI, model API and classic UI returned HTTP 200.
- Live same-origin requests passed; hostile browser Origin and Host requests returned HTTP 403.
- Playwright/Chromium at 1440×1000 loaded the Studio, dismissed the first-run welcome and CPU preflight notice, and opened Editor with its media panel and timeline. No console errors or HTTP failures were recorded. Browser plugin was unavailable; temporary Playwright tooling was used. Evidence: `/tmp/imagemaestro-editor.png`.
- Apple Silicon dependency resolution passed; no Mac execution, signing or GPU inference tested.
- The sandbox hides GPU device nodes. A host check outside the sandbox confirmed an AMD Ryzen 7 255 with Radeon 780M (HawkPoint, PCI 1002:1900), `/dev/kfd` and `/dev/dri/renderD128`. An isolated ROCm compatibility probe is recorded below.

No model generation was certified. The CUDA-specific execution paths above remain a release blocker for claiming universal Apple Silicon/CPU pipeline support.

## Host ROCm probe

PyTorch `2.9.1+rocm6.4` / HIP `6.4.43484-123eb5128` detected the host GPU as
`AMD Radeon 780M Graphics`, architecture `gfx1103`, with approximately 15.3 GiB
reported device memory. The wheel's compiled targets are `gfx900`, `gfx906`,
`gfx908`, `gfx90a`, `gfx942`, `gfx1030`, `gfx1100`, `gfx1101`, `gfx1102`,
`gfx1200`, and `gfx1201`. **gfx1103 is absent.** Compute was deliberately skipped
for the unsupported target, and no architecture override was applied. The AMD
auto-install path will reject this hardware/wheel combination with a clear error.
This machine needs an appropriate gfx1103 build or a separately validated
compatibility workaround before GPU generation can be certified.

The installed CPU preview is at `/home/jim/Work/imagemaestro-install-test`; its
application-menu launcher is installed and its test server was started on
`http://127.0.0.1:7861/`. It can browse the UI and use Editor; CPU generation is not
certified because the minimal offloader test fails on a CUDA-only operation.
