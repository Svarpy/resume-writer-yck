# Release checklist (Sprint 2)

Single source of truth: ``APP_VERSION`` in ``resume_writer/constants.py``
(e.g. ``v3.0.0``). The git tag and GitHub Release **must** use the same
``vX.Y.Z`` string.

## Cut a release (merge to ``main``)

1. On the release PR, bump ``APP_VERSION`` (and keep package ``__version__``
   imported from constants — do not hardcode a second version).
2. Merge the PR into ``main`` (Lead flow: land via ``genpubv3`` → review → ``main``).
3. On the **exact** ``main`` HEAD commit that contains that ``APP_VERSION``:

   ```bash
   git checkout main && git pull
   git tag "vX.Y.Z"   # must equal APP_VERSION, e.g. v3.0.0
   git push origin "vX.Y.Z"
   ```

4. Ensure the tag points at that HEAD (not an older commit):

   ```bash
   git rev-list -n 1 "vX.Y.Z"   # must equal git rev-parse HEAD
   ```

5. Trigger the **Release** workflow on ``main``:
   - Prefer tagging **before** / **with** the push that updates ``main`` when
     cutting locally (`git push origin main --tags`), **or**
   - After tagging a commit already on ``main``, use **Actions → Release →
     Run workflow** (`workflow_dispatch`).

6. Confirm the Release assets are named:

   - `ResumeWritervX.Y.Z.app.zip`
   - `ResumeWritervX.Y.Z.exe.zip`

Display name inside the binary/bundle: `Resume Writer vX.Y.Z`.

## What CI does

| Condition on ``main`` push | Behavior |
| --- | --- |
| HEAD has tag ``APP_VERSION`` | Tests → macOS + Windows PyInstaller (onedir) → zip → GitHub Release |
| HEAD has **no** matching ``v*`` tag | Tests only (no publish) |

Workflow file: `.github/workflows/release.yml`  
Helpers: `resume_writer/version.py`, `release/build_release.py`,
`release/check_release_tag.py`

## Signing (Sprint 2 decision)

**Ship unsigned.** Svarpy / Apple Developer ID and Windows Authenticode signing
*without* notarization is not low-complexity for CI (certs, secrets, keychain /
signtool). Hooks live in `release/sign_hooks.py` (`RESUME_WRITER_SIGN=1` later).
Users may need Gatekeeper “Open” / SmartScreen “More info” on first launch.

## Local dry-run

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python release/build_release.py --print-names
python release/check_release_tag.py
# optional full local build:
# python release/build_release.py
```
