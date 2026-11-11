# Resume Writer Documentation

> **Source of truth (Sprint 1):** This documentation has been migrated to the Notion teamspace **resume-writer-yck**.
> Maintain updates on the Notion page: https://app.notion.com/p/3e0bfc4f45de80538071d57b3bc7e75b
> This local file is retained pending Project Lead / PM approval to delete.

Version: v4 (branch `v4generic`; `APP_VERSION` in `resume_core/constants.py` is bumped at release time)

Resume Writer creates a formatted `.docx` resume from your content, in the layout of a sample document you upload. It has three front ends on one engine: a desktop app (Tkinter), a REST API (FastAPI) and an MCP server for AI apps such as Claude. Data lives in MongoDB; documents are always generated on your own computer. It keeps the resume format consistent while almost everything about it (resume sections, personal details, fonts, education, metadata, output folder and file name, duplicate checks and required fields) is controlled from a per-user Settings page whose values are stored in MongoDB.

This file is not shown inside the app. The in-app Documentation page was removed in v4.

## Contents

- [Project Layout](#project-layout)
- [What The Application Includes](#what-the-application-includes)
- [Settings](#settings)
- [Profile](#profile)
- [Generated Resume Behavior](#generated-resume-behavior)
- [Required Fields And Validation](#required-fields-and-validation)
- [Keyboard Support](#keyboard-support)
- [How To Use The Application](#how-to-use-the-application)
- [Job Experience Input Tips](#job-experience-input-tips)
- [Mac Installation](#mac-installation)
- [Windows Installation](#windows-installation)
- [Releases And Main-Merge Checklist](#releases-and-main-merge-checklist)
- [Updating Dependencies](#updating-dependencies)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)

## Project Layout

Five packages in one repository. They can be installed together or separately (see `pyproject.toml` extras).

```text
resume_core/     # the engine: OOXML parser + generator, settings schema/validation, format analysis. No I/O, no UI.
resume_server/   # FastAPI + MongoDB: accounts, tokens, formats, settings. The ONLY place with database credentials.
resume_client/   # API client + local disk cache + generation engine (shared by the desktop app and the MCP server).
resume_gui/      # Tk desktop app (talks to the client only).
resume_mcp/      # MCP server for AI apps (talks to the client only).
docs/            # documentation (not shipped inside the app)
tests/           # core / server / client / mcp / gui test suites
.env.example     # every configurable secret and address
```

Dependencies point one way: `resume_gui` / `resume_mcp` → `resume_client` → `resume_core`, and `resume_server` → `resume_core`. The client never imports the server, so the desktop bundle contains no database code or secrets.

### How the pieces work together

```text
 Claude / AI app ──MCP──▶ resume_mcp ─┐
                                      ├─▶ resume_client ──HTTP──▶ resume_server ──▶ MongoDB
 desktop app (Tk) ────────────────────┘        │
                                               └─▶ local disk cache  +  document generation on this computer
```

- **MongoDB** holds accounts (bcrypt hashes), personal access tokens (SHA-256 hashes), format metadata, the uploaded sample documents and setting overrides.
- **The server** validates everything with `resume_core` (the same rules the desktop app uses) and enforces per-user isolation.
- **Generation happens locally**: the client downloads the sample (once per revision), applies your cached settings and writes the `.docx` into your output folder on this computer. The MCP server answers the AI app with only `success` or `failure: <reason>`.
- **The desktop app and the MCP server can run at the same time**; they share the same account, the same server and the same cache folder.

### Run it

1. Create the environment file and fill in your MongoDB details and a JWT secret:

```bash
cp .env.example .env
```

2. Install (everything, or only what you need: `pip install ".[server]"`, `".[gui]"`, `".[mcp]"`):

```bash
python3 -m pip install -r requirements.txt
```

3. Start the pieces you need (each in its own terminal, or together):

```bash
python -m resume_server          # the API (needs MongoDB + .env)
python -m resume_gui             # the desktop app
python -m resume_gui --with-server   # desktop app that also starts a local API (single-machine use)
python -m resume_mcp             # the MCP server (stdio)
```

### Tests

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
```

Server tests run against an in-memory MongoDB (`mongomock`), so no database is needed.

`tests/corpus/` builds 47 text-only resumes (fresher and experienced; centered/left/table/stacked headers, 9 heading styles, bullet styles including list numbering, 8 ways of placing dates, 5 skills layouts, two-column sidebar and table-row layouts, headers/footers, content controls, fragmented runs, numbered/colon headings, date-first lines) and checks each one: sections and kinds are understood; new content (different amounts, special characters, minimal) lands under the right headings with the sample's own formatting and date punctuation; no sample text remains; the sanitised copy gives identical output; and a generated resume is a valid sample again. Run it on its own with `python -m tests.corpus.run_corpus`.

### Configuration (`.env`)

| Variable | Used by | Meaning |
| --- | --- | --- |
| `MONGODB_URI`, `MONGODB_DB` | server | MongoDB connection string and database name (default `resume-writer`) |
| `JWT_SECRET` | server | signs login tokens (min. 24 characters; the server refuses to start with the placeholder) |
| `JWT_EXPIRE_HOURS`, `API_HOST`, `API_PORT`, `MAX_UPLOAD_MB` | server | token lifetime, bind address, upload limit |
| `RW_API_URL` | desktop app, MCP | where the API is (default `http://127.0.0.1:8765`) |
| `RW_API_TOKEN` | MCP | personal access token (Profile > Access Tokens) |
| `RW_CACHE_TTL` | desktop app, MCP | seconds before cached data is re-checked (default 900) |
| `RW_DATA_DIR` | desktop app, MCP | local folder for the cache (default `~/.ResumeWriter`) |

`.env` is git-ignored; never commit it. Only the server needs `MONGODB_URI` and `JWT_SECRET`.

### Backup

**Download Backup** is a button pinned to the bottom of the left-hand list on the Settings page (so it is always in view, whichever category is open) and is **visible only to administrators**. For every other account it does not exist: nothing on the page, no search result, and the API answers a plain `404 Not Found`, as for any address that does not exist.

Every account has a `role` in the `users` collection. New accounts get `"user"` (accounts created before roles existed are set to `"user"` when the server starts). To make someone an administrator, edit their document in MongoDB by hand and set `role` to `"admin"` (for example in Compass or `db.users.updateOne({_id: "yck"}, {$set: {role: "admin"}})`). The role is read from the database on every request, so the change applies without signing in again; the Settings page picks it up the next time it is shown.

The button asks for a folder and saves `ResWritBkpYYYYMMMDD.zip` there (for example `ResWritBkp2026Nov11.zip`; a number is added if the name already exists). The zip is a `mongodump`-style archive of the **whole database**: `<database>/<collection>.bson` plus `<collection>.metadata.json` (indexes) for every collection, `manifest.json` (document counts, who created it, app version) and a `README.txt`. Restore it with `mongorestore --db <name> <unzipped folder>/<database>`. Treat it like the database itself: it contains every user's data, password hashes and access-token hashes.

### MongoDB collections

The server creates them at start-up (indexes included); the database is `MONGODB_DB` (`resume-writer`).

| Collection | Holds |
| --- | --- |
| `users` | accounts: username, bcrypt hash, display name, email, `role` (`user` or `admin`), default format, revision counters |
| `api_tokens` | personal access tokens (SHA-256 hash and prefix only) |
| `formats` | format metadata, sections found, font/sizes, settings defaults and per-format setting overrides |
| `format_files` | the stored sample documents, with the author's personal text removed (see below) |
| `settings` | user-wide setting overrides |
| `system` | application system data, one document `_id: "app"` |

The `system` document records the version history. On every server start it lists all known versions (`versions`, oldest first, each with `version`, `status`, `released_at`, `registered_at`), marks the newest one `status: "latest"` (the others `"previous"`), and sets `current_version` (the version of the running server), `latest_version`, `api_version` and `updated_at`. A new release (a bumped `APP_VERSION`) registers itself automatically the first time its server starts; an older server never demotes a newer version already recorded. Add the release date of past versions in `VERSION_HISTORY` (`resume_core/constants.py`). The same data is public at `GET /api/v1/system`.

### Stored samples contain no personal text

When a sample is uploaded the server keeps a *sanitised* copy: the sample is regenerated through the same generator with neutral placeholder content ("Your Name", "Company Name | Location", sample bullets, example email/phone), its hyperlink addresses and document properties are cleared, and the result is stored (roughly 12-32 KB). Page setup, styles, numbering, tab stops, borders, tables, columns and headers/footers are untouched, and a resume generated from the sanitised copy is identical to one generated from the original (this is tested on every sample). If a sample cannot be sanitised without changing how it behaves, the original is stored instead and the format shows a warning.

### Local cache

Settings, the default format and its sample document are cached on this computer (`<RW_DATA_DIR>/cache/...`) so they are not fetched on every use. Each cached item remembers the server's revision numbers. A tiny `/state` request re-checks them once per `RW_CACHE_TTL`; any change replaces the stale item:

- your own changes (settings, uploading/deleting a format, changing the default) update the cache and make every local process (desktop app, MCP server) re-check immediately;
- changes made from another computer are picked up when the TTL expires;
- if the server cannot be reached, cached data is still used, so generating a resume keeps working offline (changes cannot be saved until the server is back).

### MCP server for Claude

Create an access token in the desktop app (Profile > Access Tokens), put it in `.env` as `RW_API_TOKEN`, then add the server to your MCP client. For Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "resume-writer": {
      "command": "python",
      "args": ["-m", "resume_mcp"],
      "cwd": "/path/to/ResumeWriter",
      "env": { "RW_API_URL": "http://127.0.0.1:8765", "RW_API_TOKEN": "rwt_..." }
    }
  }
}
```

Tools: `get_status`, `list_sections`, `generate_resume(company, sections)`, `check_duplicate`, `list_formats`, `set_default_format`, `upload_format(name, file_path)`, `get_settings`, `update_settings`. A typical conversation: the AI calls `list_sections`, writes the text for each section and calls `generate_resume`; the file appears in your output folder and the AI only gets `success` or `failure: <reason>`.

### REST API

Interactive documentation (Swagger UI) is served at `/docs` and ReDoc at `/redoc` while the server runs. In the desktop app, **Profile > Access Tokens > Open API Documentation** opens it in your browser. In Swagger click **Authorize**, paste an access token (or a login token from `POST /api/v1/auth/login`) and try any endpoint. Endpoints are grouped (Account, Formats, Settings, System, Cache); the backup endpoints are deliberately not listed. All data endpoints live under `/api/v1` and need `Authorization: Bearer <login token or access token>`: `/auth/signup`, `/auth/login`, `/profile`, `/tokens`, `/formats` (upload, list, default, sample download, delete), `/settings` (get, patch, reset) and `/state`.

## What The Application Includes

- A left sidebar with **Writer**, **Formatter** and **Settings**, plus **Profile** and **Sign Out** at the bottom. When the sidebar is collapsed, Profile is shown as a person icon (the letter `P` if icons are unavailable).
- **Writer**: font and size dropdowns, one text box per resume section (the sections come from Settings), the output file path, the File Name field and Generate DOCX.
- **Formatter**: saved resume formats, including formats extracted from an uploaded Word document.
- **Settings**: every customisable option, grouped by category, see [Settings](#settings).
- **Profile**: account display name, email and password, see [Profile](#profile).
- Filename status marker next to the File Name field:
  - Hidden when the File Name field is empty or the duplicate check is switched off.
  - Green tick when no matching file is found.
  - Red X when a matching file blocks generation.
- A Help menu with About (application name and version).

## Settings

Open **Settings** in the sidebar. Settings are stored per user in MongoDB (through the API) and cached on this computer. The Settings page, the MCP `get_settings` / `update_settings` tools and the REST `/settings` endpoint all use the same validated values.

The page works like the VS Code settings editor:

- Everything is validated as you type (quietly while the value is still incomplete, with an error message once you leave the field or press Return) and sent to the server in one batch a moment after you stop typing. If the server cannot be reached, the page says "Not saved yet" and keeps retrying.
- Advanced settings are hidden until you press **Show Advanced**; searching always finds them.
- Colour settings accept `#1a2b3c`, `1a2b3c`, `#abc`, `rgb(26, 43, 60)`, `26 43 60`, `hsl(210, 40%, 17%)` or a colour name such as `orange`.
- Scrolling works with the mouse anywhere on the page.

- Categories are listed alphabetically on the left, and settings are alphabetical inside each category. Pick a category to filter, or use the search box (matches name, key, description).
- Edits are validated and saved immediately. Invalid values show a message under the setting and are not saved.
- A `●` marker and a **Reset** button appear on settings that differ from the default; **Reset All** restores everything.
- **Edit settings.json** shows the complete settings as JSON. **Save** validates the whole document (unknown keys are rejected) before applying it.

| Category | Settings |
| --- | --- |
| Appearance | Dark mode, accent colour, Writer text size; advanced: sidebar startup mode and auto-collapse width |
| Duplicate Check | Enable/disable, folders to check (`{output_dir}` expands to the Output Directory), file types, case sensitivity |
| Education | List of education entries (label, include in resume, degrees); one entry can hold several degrees, separated by a blank line (date after a Tab or `\|`, institution on the next line); add, remove, reorder |
| Experience Parsing | Known companies: name, line prefixes to match, company date and per-role dates used when a pasted line has no date |
| Fonts | Font choices, name/heading/text size choices (add your own fonts and sizes) |
| Metadata | DOCX author (blank = personal name), subject, title template (`{name}`), keyword count |
| Output | Output directory, file name template, file name placeholder, date format, live "Resulting Path" preview |
| Personal Details | Name, email, phone, location shown in the resume header |
| Resume Sections | The section list: key, Writer label, DOCX heading, kind, width, shown, min/max words; add, remove, reorder |
| Validation | Which fields are required before Generate is enabled (every Writer section plus File Name) |
| Writer | Clear fields after generate |

### Settings per resume format

Some settings belong to the selected resume format (marked `format` on the page): **Resume Sections**, **Fonts** and **Required Fields**. Each saved format keeps its own copy in MongoDB; everything else (personal details, education, output, duplicate check, metadata, appearance) is shared by all formats of your account.

When a format is uploaded its defaults come from the sample: the sections found in it (headings, order, kinds), its font and sizes, and the required fields for those sections. Making a format the default switches Resume Sections, Fonts and Required Fields to that format's values; **Reset** returns to what the sample defines. Before any format exists the page shows a generic section list; it is replaced as soon as the first format is uploaded.

### Resume Sections

Each section has a **kind** that decides how it is written:

| Kind | Writer box | In the DOCX |
| --- | --- | --- |
| `paragraph` | yes | justified paragraphs |
| `skills` | yes | `Label: values` lines with a bold label |
| `experience` | yes | company / role lines with right-aligned dates, other lines as bullets |
| `bullets` | yes | bullets, dated lines or plain lines |
| `education` | no (filled from Settings > Education) | one block per included education entry |
| `keywords` | yes | not written; the first *Keyword Count* entries become DOCX keywords |

Order in the list is the order in the resume. A blank *DOCX heading* uses the selected format's own heading (or the label for a section the format does not have). Advanced fields: *Key*, *Width* and *Show heading* (untick to write the section without a heading). Empty sections are skipped when the resume is written. Only one `education` and one `keywords` section may exist. For formats whose sections are plain paragraphs the order set here is used. For formats laid out in table cells (for example headings in different table rows) the sample's own order is kept, because moving content between cells would break the layout.

### File names

`output.filename_template` is expanded with these placeholders and `.docx` is appended: `{company}` (the Writer File Name field, or the placeholder setting when empty; required in the template), `{date}` (the date format setting), `{name}` (personal name) and `{username}`. The default template is `Resume{company}{date}`, for example `ResumeAcme09Nov.docx`.

### Example `settings.json` (shortened)

```json
{
  "version": 1,
  "output": {
    "directory": "/Users/me/Documents/Resumes",
    "filename_template": "Resume{company}{date}",
    "company_placeholder": "XXX",
    "date_format": "%d%b"
  },
  "personal": { "name": "Ada Lovelace", "email": "ada@example.com", "phone": "", "location": "London" },
  "validation": { "required_fields": ["summary", "skills", "experience", "top_skills", "file_name"] }
}
```

## Formatter And Resume Formats

There is no built-in resume format. On first use, open the **Formatter** and click **Add Format** to upload a Word document that has the layout you want. The first format you upload becomes your **default** and is the one the Writer uses. Upload more at any time and press **Make Default** (or choose it in the Default Format box) to switch; Resume Sections, Fonts and Required Fields in Settings switch with it. Deleting the default format makes the oldest remaining one the default; with none left the Writer asks for an upload again.

Each uploaded document is kept and used as the template for every resume generated with that format.

The sample is read at the OOXML level (`resume_core/ooxml/`): the parser finds the name, an optional tagline, the contact line, every section (heading, separator before it, content) and, for each kind of line, an exemplar taken from the sample itself: a paragraph, a bullet, a `Label: values` skill line, a company/role row with a date (tab based, two-cell table, or text plus a separate date line), a role gap and a plain line. Headings are recognised by name (summary, skills, experience, education, certifications, projects and many aliases) and by how they look (style, bold/caps, border), so uncommon samples work too.

Generation copies the sample document and rebuilds only the text: every exemplar is cloned and just its text changes. Page setup, styles, numbering, tab stops, borders, table layouts (including multi-column skills), headers/footers and run formatting therefore come from the sample. Details:

- Name, tagline and contact items are replaced in place (blank items are dropped with their separator; email/phone hyperlinks are retargeted). Personal details found in headers or footers are replaced too.
- Sections with no text are left out; sections the sample does not have are added using its heading and line styles; sections you hide are removed.
- Table cells that held several columns of content (such as two columns of skills) are refilled column by column.
- A line like `Company | Location` keeps its bold/normal run formatting segment by segment.

Limits: formats are not previewed in the app; very unusual samples (text boxes, content only in drawings) may not be understood, in which case the Formatter shows what was detected. Check generated resumes in Word before sending them.

## Profile

Open **Profile** from the sidebar (above Sign Out). It holds the account display name, email, the password change form and **Access Tokens**. The name, email, phone and location written on the resume are separate and live in Settings > Personal Details; they are filled from the account's display name and email at sign-up.

Access tokens let the MCP server (or any API client) use your account without your password. Create one, copy it (it is shown once and stored only as a hash), and put it in `RW_API_TOKEN`. Revoke it here at any time.

Sign-in: Enter submits the form from any field. The username (and, while the app stays open, the password) remains filled after Sign Out; only the username is remembered between launches, and the password is never written to disk.

## Generated Resume Behavior

The app generates a local Word document in `.docx` format.

- Output folder: Settings > Output > Output Directory (default `~/Documents/Resumes`). *Browse* on the Writer page changes this setting.
- File name: built from the file name template (see [File names](#file-names)).
- Duplicate check (Settings > Duplicate Check): when enabled, Generate stays disabled while a file whose name contains the File Name value exists in any of the configured folders with one of the configured extensions. Defaults: the output folder and its `#applied` subfolder, `.docx` and `.pdf`, case-insensitive. Folders are never created by the check.

The generated resume includes:

- The name at the top and, under it, email, phone and location separated by `|` (blank details are left out). Email is hyperlinked with `mailto:` and phone with `tel:`.
- Horizontal separator lines between resume sections.
- The sections from Settings > Resume Sections, in order, each with its heading.
- Experience bullet points are created automatically for non-date lines, and spaced em-dashes like ` — ` in them are converted to `, `.
- Pasted dates in Job Experience are preserved before any Known Companies fallback dates are applied.

The generated `.docx` metadata comes from Settings > Metadata:

- Author: the Author setting, or the personal name when blank.
- Subject, Title (from the title template) and Keywords (the first *Keyword Count* entries of the keywords section).

## Required Fields And Validation

The Generate DOCX button (and the keyboard shortcut) stays disabled until every condition is met. Which fields are required is controlled in Settings > Validation; by default Summary, Skills, Job Experience, the keywords section and File Name are required.

- A required Writer section must not be empty.
- A section with word limits (Settings > Resume Sections; Summary defaults to 41-50 words) must be within them whenever it has text. The Writer page shows the current word count under such a section.
- File Name must be filled when it is required; when it is blank the file name keeps the placeholder (`XXX`).
- The output file path must be set.
- No matching file may exist when the duplicate check is enabled.

## Keyboard Support

- Press `Tab` inside a text box to move to the next field.
- Press `Shift+Tab` to move to the previous field.
- On Mac, press `Command+Return` to generate the DOCX when the form is valid.
- On Windows or Linux, press `Ctrl+Enter` to generate the DOCX when the form is valid.

## How To Use The Application

1. Open **Settings** once and fill in Personal Details, Education, Output Directory and anything else you want to change.
2. On **Writer**, choose the resume font, name size, heading size, and text size.
3. Fill in the section text boxes. Required sections and word limits are shown in the status text.
4. Review the output filepath preview.
5. Enter the target company or file name value in the File Name field.
6. Click Generate DOCX.

After the file is generated successfully, the app clears the text boxes and the File Name field (switch this off in Settings > Writer). The filepath preview stays on the last generated file for reference.

## Job Experience Input Tips

Use one item per line.

For company or role lines with dates, use one of these formats:

```text
Acme Corp | Atlanta, GA January 2025 - May 2026
Acme Corp | Atlanta, GA | January 2025 - May 2026
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

If a company or role line has no date, dates can be filled in from Settings > Experience Parsing > Known Companies (a line matches a company when it starts with one of its configured prefixes). With no known companies configured, undated lines are simply bullets.

## Building The Desktop App

The desktop bundle is a client only: it is built without the server, MongoDB drivers or the MCP package.

```bash
python3 -m pip install -r requirements.txt
python3 release/build_release.py
```

Run the server separately (your own machine, a VPS or a container) and point the app at it with `RW_API_URL`. On first launch macOS may block a locally built app: right-click it in Finder and choose Open. On Windows choose More info > Run anyway for unsigned builds.

## Releases And Main-Merge Checklist

Canonical operator checklist: repo root **`RELEASE.md`** (keep that file in sync with this section).

### Version contract

- Single source of truth: `APP_VERSION` in `resume_core/constants.py` (for example `v3.0.0`).
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

Feature / `genpubv3` pushes do not publish releases. Workflow: `.github/workflows/release.yml`. Helpers: `resume_core/version.py`, `release/build_release.py`, `release/check_release_tag.py`.

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
- Generated resumes are written only to your own computer, never to the server. Only the server holds the MongoDB credentials and the JWT secret (`.env`, git-ignored); the desktop app and the MCP server talk to the API with a login or access token.
- Passwords are stored as bcrypt hashes and access tokens as SHA-256 hashes. Use HTTPS (a reverse proxy) when the API is reachable from other machines, and keep `JWT_SECRET` private.
- Review the generated `.docx` before sending it to employers.
- Official installers are published as **unsigned** GitHub Release zips in Sprint 2; prefer downloading from the `Svarpy/resume-writer-yck` Releases page. Expect Gatekeeper / SmartScreen prompts on first launch (see Releases And Main-Merge Checklist).

## Troubleshooting

### The App Says It Cannot Reach The Server

Start the API (`python -m resume_server`, or run the app with `--with-server`) and check `RW_API_URL`. With a warm cache you can still generate resumes; saving changes needs the server. Server start-up errors name the missing `.env` value or the MongoDB address that could not be reached.

### The MCP Server Returns `failure: ...`

The reason is the message to act on: for example no format uploaded yet, a required section missing, a matching file already present, or an invalid/revoked `RW_API_TOKEN`.

### Tk Deprecation Warning On Mac

Some macOS Python installations may show a Tk warning when starting the app. The app sets `TK_SILENCE_DEPRECATION=1` to suppress the warning where possible.

If Tk still behaves incorrectly, use the latest official Python installer from `python.org` and run the app from a fresh virtual environment.

### Generate DOCX Button Is Disabled

The status text under the Writer page lists what is missing. Check that:

- Every section marked required in Settings > Validation is filled.
- Sections with word limits (Summary defaults to 41-50 words) are within them.
- File Name is filled, if it is required.
- No matching file exists in the folders listed in Settings > Duplicate Check (or switch the check off there).

### Red X Beside File Name

The red X means a matching file may already exist. By default the match is case-insensitive and checks `.docx` and `.pdf` files in the output folder and its `#applied` folder; folders, file types and case sensitivity are set in Settings > Duplicate Check.

Use a different File Name value, move/archive the matching file, or change the duplicate check settings.

### A Setting Will Not Save

The message under the setting says why (for example a file name template without `{company}`). Nothing is written until the value is valid. If `settings.json` was edited by hand and cannot be read, the app renames it to `settings.json.broken` and starts from the defaults.

### Dates In Job Experience Look Wrong

Use a clear date format on company or role lines:

```text
Company Name | Location | January 2025 - May 2026
Role Name | January 2025 - May 2026
```

Pasted dates should be preserved. Fallback dates are only used for lines that match a Known Company in Settings and do not include a date.

### macOS Blocks The Downloaded App

Right-click the app in Finder and choose **Open** (Gatekeeper). Sprint 2 builds are unsigned.

### Windows SmartScreen Blocks The App

Choose **More info** → **Run anyway**. Sprint 2 builds are unsigned.
