# Release checklist (Sprint 2)

Single source of truth: ``APP_VERSION`` in ``resume_writer/constants.py``
(e.g. ``v3.0.0`` or ``v3.0.0Beta2``). The git tag and GitHub Release **must**
use the same string (``vX.Y.Z`` or ``vX.Y.ZBetaN``).

## TEMPORARY — Beta2 test on ``genpubv3``

For the **v3.0.0Beta2** test cut only, `.github/workflows/release.yml` triggers
on pushes to **``genpubv3``** (not ``main``). Do **not** merge this Beta2 cut
to ``main``. After the test, revert the workflow branch filter to ``main``.

Beta2 publishes a **normal** GitHub Release (no ``prerelease: true`` flag) so
the in-app updater — which skips GitHub prereleases — can install it. The tag
form ``v3.0.0Beta2`` is still a pre-release *version* relative to ``v3.0.0``.

Asset example: ``ResumeWriterv3.0.0Beta2.app.zip``.

## Cut a release (Beta2 test: merge to ``genpubv3``)

1. On the release branch, bump ``APP_VERSION`` (and keep package ``__version__``
   imported from constants — do not hardcode a second version).
2. Merge into ``genpubv3`` (temporary Beta2 path; production cuts use ``main``).
3. On the **exact** ``genpubv3`` HEAD commit that contains that ``APP_VERSION``:

   ```bash
   git checkout genpubv3 && git pull
   git tag "vX.Y.ZBetaN"   # must equal APP_VERSION, e.g. v3.0.0Beta2
   git push origin genpubv3
   git push origin "vX.Y.ZBetaN"
   ```

4. Ensure the tag points at that HEAD (not an older commit):

   ```bash
   git rev-list -n 1 "v3.0.0Beta2"   # must equal git rev-parse HEAD
   ```

5. Trigger the **Release** workflow on ``genpubv3``:
   - Prefer tagging **before** / **with** the push that updates ``genpubv3``
     when cutting locally, **or**
   - After tagging a commit already on ``genpubv3``, use **Actions → Release →
     Run workflow** (`workflow_dispatch`).

6. Confirm the Release assets are named:

   - `ResumeWritervX.Y.ZBetaN.app.zip` (e.g. `ResumeWriterv3.0.0Beta2.app.zip`)
   - `ResumeWritervX.Y.ZBetaN.exe.zip`

Display name inside the binary/bundle: `Resume Writer vX.Y.ZBetaN`.

## Production cut (after Beta2 — revert trigger to ``main``)

1. Revert workflow ``on.push.branches`` to ``main``.
2. Bump ``APP_VERSION`` to a plain ``vX.Y.Z``.
3. Merge via ``genpubv3`` → review → ``main``, then tag ``main`` HEAD with the
   same ``APP_VERSION`` string and push the tag.

## What CI does

| Condition on ``genpubv3`` push (temporary) | Behavior |
| --- | --- |
| HEAD has tag ``APP_VERSION`` | Tests → macOS + Windows PyInstaller (onedir) → zip → GitHub Release |
| HEAD has **no** matching tag | Tests only (no publish) |

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
