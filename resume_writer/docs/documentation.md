# Resume Writer Documentation

> **Source of truth (Sprint 1):** This documentation has been migrated to the Notion teamspace **resume-writer-yck**.
> Maintain updates on the Notion page: https://app.notion.com/p/3e0bfc4f45de80538071d57b3bc7e75b
> This local file is retained pending Project Lead / PM approval to delete.

Version: v3.0.0

Resume Writer is a desktop application for creating a formatted `.docx` resume from user-provided content. It is designed to keep the resume format consistent while allowing the main content, header details, education selections, certifications, and output file path to be edited from the app.

## Contents

- [Project Layout](#project-layout)
- [What The Application Includes](#what-the-application-includes)
- [Generated Resume Behavior](#generated-resume-behavior)
- [Required Fields And Validation](#required-fields-and-validation)
- [Keyboard Support](#keyboard-support)
- [How To Use The Application](#how-to-use-the-application)
- [Job Experience Input Tips](#job-experience-input-tips)
- [Mac Installation](#mac-installation)
- [Windows Installation](#windows-installation)
- [Auto-Update (In-App)](#auto-update-in-app)
- [Releases And Main-Merge Checklist](#releases-and-main-merge-checklist)
- [Updating Dependencies](#updating-dependencies)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)

## Project Layout

Pre–Sprint 2 package refactor on `genpubv3` (structure and hygiene only; no feature changes). Application code lives under the `resume_writer/` package. Repo-root modules such as `resume_writer_app.py`, `ui_*.py`, `user_auth.py`, `formats_store.py`, and `app_paths.py` are thin entrypoints or compatibility shims. Sprint 2 adds `resume_writer/update/` (GitHub Releases auto-updater) and `RELEASE.md` (main-merge release checklist). Documented against `genpubv3` @ `c5aec13`.

### Package tree

```text
resume_writer/
  __main__.py          # python -m resume_writer
  constants.py         # APP_VERSION (single source of truth)
  paths.py             # app data directory helpers
  version.py           # version compare + Release asset names
  auth/                # user auth service
  docs/                # in-app documentation.md + loader
  formats/             # saved formats store / extract / models
  render/              # DOCX build, parse, template apply
  ui/                  # Tk shell, Writer, Formatter, Settings, auth UI
  update/              # in-app GitHub Releases auto-updater
tests/                 # unittest suite + fixtures
RELEASE.md             # cut-a-release checklist (main merge + tag)
.github/workflows/release.yml
```

### How to run

```bash
python3 resume_writer_app.py
# or
python3 -m resume_writer
```

### Tests

```bash
python -m unittest discover -s tests
```

### Layer rule

Dependencies should point downward only:

`ui` → `render` → `formats` → `auth` → `paths`

Lower layers must not import higher ones (for example `paths` must not import `ui`). Compat shims at the repo root re-export package symbols for older imports and tests.

## What The Application Includes

- Font controls for the generated resume:
  - Font
  - Name Size
  - Heading Size
  - Text Size
- Dark mode by default, with a Light/Dark mode toggle.
- Required content fields:
  - Summary
  - Skills
  - Job Experience
  - Top 5 Skills For Metadata
- Optional content field:
  - Certifications
- Editable header fields:
  - Name
  - Email
  - Phone
  - Location
- Selectable education entries:
  - Masters is selected by default.
  - Bachelors can be selected when needed.
  - Each education entry can be edited by clicking its edit symbol.
- Output folder picker with a generated filepath preview and a focused file-name field for the company portion of the resume filename.
- Filename status marker:
  - Hidden when the file-name field is empty.
  - Green tick when no matching file is found.
  - Red X when a matching file blocks generation.
- Help menu with usage guidance.
- About menu with application name and current version.

## Generated Resume Behavior

The app generates a local Word document in `.docx` format.

- Default output folder:
  `/Users/yck/Desktop/CLGENAPPL`
- Default file name format:
  `YcKResumeXXXDDMMM.docx`
- `XXX` is the company placeholder. The app provides a file-name field for this portion only.
- `DD` is the current day.
- `MMM` is the current month abbreviation, such as `Jul`, `Aug`, or `Sep`.
- The selected output folder is shown as part of the filepath preview.
- Duplicate filename checks look for matching `.docx` and `.pdf` files in:
  - the selected output folder
  - the selected output folder's `#applied` folder
- The duplicate check is case-insensitive and checks whether the entered file-name value appears anywhere in an existing filename.
- If `#applied` does not exist, the app creates it during validation.

The generated resume includes:

- Name at the top.
- Email, phone number, and location under the name, separated by `|`.
- Email is hyperlinked with `mailto:`.
- Phone number is hyperlinked with `tel:`.
- Horizontal separator lines between resume sections.
- Uppercase section headings:
  - SUMMARY
  - SKILLS
  - WORK EXPERIENCE
  - EDUCATION
- Certifications are added after Education only when the Certifications field has content.
- Summary, Work Experience, and Education content are justified where applicable.
- Skills and header content are left aligned.
- Job Experience bullet points are created automatically for non-date lines.
- In Job Experience bullet points, spaced em-dashes like ` — ` are converted to `, `.
- Pasted dates in Job Experience are preserved before fallback date defaults are applied.

The generated `.docx` metadata includes:

- Author: the name entered in the header field.
- Subject: `my resume`
- Keywords: the first five skills entered in the Top 5 Skills For Metadata field.

## Required Fields And Validation

The Generate DOCX button is disabled until all required conditions are met.

Required fields:

- Summary
- Skills
- Job Experience
- Top 5 Skills For Metadata

Output validation:

- If the file-name field is blank, the generated filename keeps `XXX`.
- If the file-name field has content, the app updates the filepath preview with that value.
- If a matching `.docx` or `.pdf` already exists in the selected output folder or `#applied`, Generate DOCX stays disabled.

Summary requirement:

- Must be more than 40 words.
- Must be 50 words or fewer.
- The app shows the current Summary word count below the Summary field.

Keyboard shortcuts are also disabled until the required conditions are met.

## Keyboard Support

- Press `Tab` inside a text box to move to the next field.
- Press `Shift+Tab` to move to the previous field.
- On Mac, press `Command+Return` to generate the DOCX when the form is valid.
- On Windows or Linux, press `Ctrl+Enter` to generate the DOCX when the form is valid.

## How To Use The Application

1. Open the app.
2. Choose the resume font, name size, heading size, and text size.
3. Enter or paste the Summary.
4. Confirm the Summary word count is between 41 and 50 words.
5. Enter or paste Skills.
6. Enter or paste Job Experience.
7. Enter Certifications if needed.
8. Enter the Top 5 Skills For Metadata.
9. Review the output filepath preview.
10. Enter the target company or filename value in the File Name field.
11. Edit the header fields if needed.
12. Select Masters and/or Bachelors in the education section.
13. Edit education details if needed by clicking the edit symbol.
14. Click Generate DOCX.

After the file is generated successfully, the app clears the content input fields and the File Name field so the next resume can be started cleanly. The filepath preview remains on the last generated file for reference.

## Job Experience Input Tips

Use one item per line.

For company or role lines with dates, use one of these formats:

```text
First Horizon Bank | Atlanta, GA January 2025 - May 2026
First Horizon Bank | Atlanta, GA | January 2025 - May 2026
Software Engineer - Full Stack | January 2025 - May 2026
```

The app aligns the left side and date side in the generated document using fixed left/right columns. The date column is kept wide enough to prevent normal date ranges from wrapping.

For achievement lines, paste each point on its own line:

```text
Built and maintained internal developer tooling using React and Java Spring Boot APIs.
Designed RESTful APIs consumed by internal dashboards.
Improved deployment consistency across development and staging environments.
```

The app adds bullets automatically.

## Mac Installation

### Option 1: Run From Source

1. Install Python 3 from the official Python website:
   `https://www.python.org/downloads/macos/`
2. Open Terminal.
3. Go to the application folder:

```bash
cd /Users/yck/Documents/ResumeWriter
```

4. Create a virtual environment:

```bash
python3 -m venv .venv
```

5. Activate the virtual environment:

```bash
source .venv/bin/activate
```

6. Upgrade packaging tools:

```bash
python -m pip install --upgrade pip setuptools wheel
```

7. Install application dependencies:

```bash
python -m pip install -r requirements.txt
```

8. Start the app:

```bash
python3 resume_writer_app.py
# or
python3 -m resume_writer
```

### Option 2: Build A Mac App

From the activated virtual environment:

```bash
pyinstaller --windowed --name "Resume Writer" resume_writer_app.py
```

The generated app will be available in:

```text
dist/Resume Writer.app
```

If macOS blocks the app because it was built locally, open it from Finder by right-clicking the app and choosing Open.

## Windows Installation

### Option 1: Run From Source

1. Install Python 3 from the official Python website:
   `https://www.python.org/downloads/windows/`
2. During installation, select Add Python To PATH.
3. Open Command Prompt or PowerShell.
4. Go to the application folder:

```powershell
cd path\to\ResumeWriter
```

5. Create a virtual environment:

```powershell
py -m venv .venv
```

6. Activate the virtual environment:

```powershell
.venv\Scripts\activate
```

7. Upgrade packaging tools:

```powershell
python -m pip install --upgrade pip setuptools wheel
```

8. Install application dependencies:

```powershell
python -m pip install -r requirements.txt
```

9. Start the app:

```powershell
python resume_writer_app.py
# or
python -m resume_writer
```

### Option 2: Build A Windows App

From the activated virtual environment:

```powershell
pyinstaller --windowed --name "Resume Writer" resume_writer_app.py
```

The generated executable will be available in:

```text
dist\Resume Writer\Resume Writer.exe
```

## Auto-Update (In-App)

Sprint 2 ships a weekly in-app updater that checks **public** GitHub Releases for the `Svarpy/resume-writer-yck` repository (no auth token).

### When the check runs

- After the main shell is ready, the app schedules a background check (`resume_writer/update/`).
- Checks run at most once every **7 days** (state file `update_state.json` under the app data root).
- Network / API failures fail soft: the previous install is kept, and the last-check timestamp is **not** advanced (retry on a later launch).

### Install Now / Remind Later

When a newer release has an OS-matching asset, the app shows an **Update Available** dialog:

- **Install Now** — download → verify zip → replace the current install → cleanup → relaunch. On failure, the previous install is kept and an error is shown.
- **Remind Later** — dismisses the dialog and records the check so the prompt will not reappear until the next weekly interval.

Closing the dialog is treated like **Remind Later**.

Draft and prerelease GitHub Releases are ignored. Only releases newer than the running `APP_VERSION` with the correct platform asset are offered.

### Release asset names the updater expects

| Platform | GitHub Release asset |
| --- | --- |
| macOS | `ResumeWritervX.Y.Z.app.zip` |
| Windows | `ResumeWritervX.Y.Z.exe.zip` |

Display name inside the binary/bundle: `Resume Writer vX.Y.Z`.

## Releases And Main-Merge Checklist

Canonical operator checklist: repo root **`RELEASE.md`** (keep that file in sync with this section).

### Version contract

- Single source of truth: `APP_VERSION` in `resume_writer/constants.py` (for example `v3.0.0`).
- Package `__version__` must import from constants — do not hardcode a second version.
- The git tag and GitHub Release **must** use the same `vX.Y.Z` string.

### Cut a release (merge to `main`)

1. On the release PR, bump `APP_VERSION`.
2. Merge into `main` (Lead flow: land via `genpubv3` → review → `main`).
3. On the **exact** `main` HEAD commit that contains that `APP_VERSION`, tag and push:

```bash
git checkout main && git pull
git tag "vX.Y.Z"   # must equal APP_VERSION
git push origin "vX.Y.Z"
```

4. Confirm the tag points at that HEAD (`git rev-list -n 1 "vX.Y.Z"` equals `git rev-parse HEAD`).
5. Trigger the **Release** workflow on `main` (tag with the push, or **Actions → Release → Run workflow**).
6. Confirm Release assets are named `ResumeWritervX.Y.Z.app.zip` and `ResumeWritervX.Y.Z.exe.zip`.

### What CI does on `main`

| Condition | Behavior |
| --- | --- |
| HEAD has tag matching `APP_VERSION` | Tests → macOS + Windows PyInstaller (onedir) → zip → GitHub Release |
| HEAD has no matching `v*` tag | Tests only (no publish) |

Feature / `genpubv3` pushes do not publish releases. Workflow: `.github/workflows/release.yml`. Helpers: `resume_writer/version.py`, `release/build_release.py`, `release/check_release_tag.py`.

### Unsigned builds (Sprint 2)

**Ship unsigned.** Signing / notarization is deferred (`release/sign_hooks.py`, `RESUME_WRITER_SIGN=1` later).

- **macOS:** users may need Gatekeeper **Open** (right-click → Open) on first launch.
- **Windows:** users may need SmartScreen **More info** → Run anyway on first launch.

## Updating Dependencies

Use a virtual environment before installing or updating dependencies.

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install --upgrade -r requirements.txt
```

After updating dependencies, run the app and generate a test `.docx` before using it for a real resume.

## Security Notes

- Install Python only from the official Python website or a trusted package manager.
- Use a virtual environment so dependencies stay isolated from the system Python installation.
- Keep `requirements.txt` small and reviewed.
- Do not paste private or sensitive content into unknown third-party tools.
- Generated resumes are written locally to the selected output path.
- Review the generated `.docx` before sending it to employers.
- Official installers are published as **unsigned** GitHub Release zips in Sprint 2; prefer downloading from the `Svarpy/resume-writer-yck` Releases page. Expect Gatekeeper / SmartScreen prompts on first launch (see Releases And Main-Merge Checklist).

## Troubleshooting

### Tk Deprecation Warning On Mac

Some macOS Python installations may show a Tk warning when starting the app. The app sets `TK_SILENCE_DEPRECATION=1` to suppress the warning where possible.

If Tk still behaves incorrectly, use the latest official Python installer from `python.org` and run the app from a fresh virtual environment.

### Generate DOCX Button Is Disabled

Check that:

- Summary is filled.
- Summary has 41-50 words.
- Skills is filled.
- Job Experience is filled.
- Top 5 Skills For Metadata is filled.
- Output file path is filled.
- No matching `.docx` or `.pdf` exists in the selected output folder or its `#applied` folder for the entered File Name value.

### Red X Beside File Name

The red X means a matching file may already exist. The match is case-insensitive and checks both `.docx` and `.pdf` files in the selected output folder and its `#applied` folder.

Use a different File Name value, move/archive the matching file, or choose a different output folder.

### Dates In Job Experience Look Wrong

Use a clear date format on company or role lines:

```text
Company Name | Location | January 2025 - May 2026
Role Name | January 2025 - May 2026
```

Pasted dates should be preserved. Fallback dates are only used when a known company or role line does not include a date.

### Update Check Never Appears

- The weekly interval may not have elapsed yet (`update_state.json` under the app data directory).
- There may be no newer public release, or the release may lack the OS-specific asset name.
- Network errors fail soft; try again on a later launch.

### macOS Blocks The Downloaded App / Update

Right-click the app in Finder and choose **Open** (Gatekeeper). Sprint 2 builds are unsigned.

### Windows SmartScreen Blocks The App

Choose **More info** → **Run anyway**. Sprint 2 builds are unsigned.
