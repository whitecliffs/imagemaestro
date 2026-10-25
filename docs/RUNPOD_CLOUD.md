# ImageMaestro Cloud GPU — implementation and deployment

## Implemented plan

- Standard-library-only local launcher, independent of the local AI engine.
- Account-key validation, owner-only credential storage, live NVIDIA prices and stock from Runpod REST v2, Secure/Community selection, optional existing network-volume selection.
- Explicit charge acceptance tied to a five-minute quote; one tracked Pod at a time; persisted deployment intent prevents duplicate billable creation after timeouts. Interrupted responses can be reconciled by the unique Pod name.
- Per-session Pod authentication covering API, assets, classic UI and WebSockets. The browser receives Secure/HttpOnly/SameSite cookies; login uses a fragment token removed before authentication. The account API key never enters the Pod or its image.
- Ready-state checks, session estimates, idle stop that checks generation/Director/download activity, and a maximum session duration. Local monitoring must remain running and online; these controls are not guaranteed billing caps.
- Download gallery outputs to `~/Downloads/ImageMaestro/<pod-id>` before stopping. Completed files are preserved, partial downloads are discarded, and filenames cannot escape the destination. This exports gallery media, not project files, LoRAs, settings or metadata sidecars; retain the volume for those.
- Explicit stop preserves Pod storage. Release requires a second confirmation and deletes the Pod disk; attached network volumes survive and continue billing. Resuming stopped Pods is currently done in the Runpod console.
- Cloud-only installation and desktop launcher, plus an entry point from the local Studio.
- NVIDIA container recipe and manually triggered GitHub build/publish workflow. Container startup checks authentication, prepares persistent app data under `/workspace/imagemaestro`, and drops privileges before loading application/model code.

## Start locally

`python3 cloud_launcher.py` opens `http://127.0.0.1:7870/cloud` without importing Torch.
`python3 run.py --cloud` is equivalent. Keep its terminal/process and this computer
online until the Pod is confirmed stopped. Cloud mode never provisions resources
merely by opening the UI or connecting an account.

For a packaged cloud-only installation, pass `--cloud-only` to the Linux `.run` or
Mac `.command` installer. This installs a small private Python runtime and Cloud
application launcher without the local AI dependencies. A normal full installation
adds both launchers. `python3 install.py --cloud-only` can also create the shortcut
when a suitable Python is already available.

`cloud/config.json` holds public publisher configuration only. The signup URL is
`https://runpod.io?ref=gnx5i108`. Existing users connect their own account normally.
Commission eligibility remains governed by Runpod's programme; attribution is not
added to deployment API calls. No revenue or referral attribution is guaranteed.

The account key and session state are stored under `~/.config/imagemaestro/cloud`
with owner-only file permissions. They are not encrypted at rest. Never share that
directory; it contains the account key and active Pod session password. No keys are
stored in browser local storage or Git. The local endpoint refuses other Host names,
cross-origin browser requests and mutations missing its custom header.

## Publish the image

Use a public GitHub repository you control. The manually triggered
`.github/workflows/runpod-image.yml` builds `cloud/Dockerfile` for Linux amd64.
With `publish=true`, it pushes `ghcr.io/<owner>/<repository>:runpod-preview` using
GitHub's scoped workflow token. Make the package public so Runpod can pull without
registry credentials. Public source/package visibility does not make user data or
credentials public: the Docker context excludes runtime data, keys and local models.

Prefer a tested immutable `@sha256:...` image reference in `cloud/config.json`.
`IMAGEMAESTRO_RUNPOD_IMAGE` can override it for publisher testing. Leave the image
blank until it has built successfully; the UI then explains why Start is unavailable.
A registry entry alone does not establish successful model generation.

The container uses CUDA 12.8 PyTorch wheels and requests hosts with CUDA >=12.8.
Only port 8080/http is exposed. SSH/Jupyter are not enabled. The actual app source,
model registry and user data live under the persistent volume's `imagemaestro/app`
subdirectory; compiled UI stays in the image. Do not remove or release that volume
until important data has been exported.

## What Google Drive can do

Google Drive is suitable as an optional export/backup destination, not as the OCI
container registry used to boot a Runpod Pod. Drive backup/OAuth is not implemented
in this first version. Download outputs locally first; a later integration can copy
finished outputs to a selected Drive folder. Active model caches stay on the Pod or
network volume for predictable access. GHCR public container storage/bandwidth is
currently free, while Actions usage is governed separately by GitHub's plan.

## Verification and remaining limits

Focused automated tests use a fake provider and real local HTTP/ASGI checks; they
never provision a paid resource. A real account/container/GPU test is still required
for pricing/placement, proxy cookies, model loading, generation, download throughput
and shutdown billing. Availability and displayed quotes may change before allocation;
the displayed session estimate excludes separate storage/tax and is not an invoice.

The earlier security review still applies. This is a preview: authentication reduces
public exposure but does not repair every upstream model-loader or dependency
advisory. Use trusted models and media; do not market it as a security-cleared release.
A failed or ambiguous create remains tracked rather than permitting a blind retry;
if reconciliation cannot find it, resolve the outcome in the Runpod console before
manually resetting local state. The launcher does not auto-delete volumes.

Official API reference:
- https://docs.runpod.io/api-reference-v2/pods/create-a-pod
- https://docs.runpod.io/api-reference-v2/catalog/list-gpu-types
- https://docs.runpod.io/api-reference-v2/pods/trigger-a-pod-state-transition
- https://docs.runpod.io/api-reference-v2/network-volumes/list-network-volumes
