# Resume Writer

A small Python desktop application that collects resume content and writes a `.docx` file locally.

## Features

- Desktop app (Tkinter) with a sidebar: **Writer**, **Formatter**, **Settings**, and **Profile** / **Sign Out** at the bottom (the collapsed sidebar shows a person icon for Profile). You stay signed in across restarts until you sign out; the wheel or trackpad scrolls any page with the pointer anywhere on it.
- Local accounts: each user has their own profile, saved formats and settings.
- **Writer**: dropdowns for font, name size, heading size and text size, and one text box per resume section. Keyboard support: Tab moves between fields, and Command+Return on Mac or Ctrl+Enter on Windows/Linux generates the DOCX when valid.
- **Settings** (saved per user as `settings.json`, edited VS Code style with search, categories, reset and a raw JSON editor) controls almost everything:
  - Appearance (dark mode, accent colours, sidebar behaviour, Writer text size)
  - Resume Sections: add, rename, reorder, hide, set the heading, kind, word limits
  - Fonts and sizes offered on the Writer page (add your own)
  - Personal Details (name, email, phone, location) and Education entries
  - Metadata (author, subject, title template, keyword count)
  - Output directory, file name template and placeholders, with a live path preview
  - Duplicate check (on/off, folders, file types, case sensitivity)
  - Validation: which fields are required
  - Known companies for filling dates on undated Job Experience lines
- Generate stays disabled until the required fields are complete and any per-section word limits are met (Summary defaults to 41-50 words).
- Dated Job Experience lines such as `Company | Location January 2025 - May 2026` are aligned with fixed left/right columns, and all other lines become bullets by default. In experience bullets, spaced em-dashes (` — `) become `, `.
- Email and phone hyperlinks and horizontal separator rules in the generated Word file.
- DOCX metadata (author, subject, title, keywords) comes from Settings > Metadata.
- Formatter: there is no built-in format. A format is a Word *template*: your resume with `{{placeholders}}` instead of the person's details (see [docs/format-templates.md](docs/format-templates.md); the app can copy a prompt that makes an AI tool convert any sample resume into one). Upload it once (it becomes the default; change the default any time), download it to edit it and replace it in place. Every resume generated with a format is the template's own layout filled with your content. Sections, fonts and required fields are settings per format.

## Architecture

Three front ends on one engine, with MongoDB for data and the local computer for documents:

| Package | What it is |
| --- | --- |
| `resume_core` | The engine: template reader and filler, settings schema and validation. No I/O. |
| `resume_server` | FastAPI + MongoDB: accounts, access tokens, formats, settings. The only place with database credentials. |
| `resume_client` | API client + local disk cache + the generation engine used by the GUI and MCP. |
| `resume_gui` | The Tk desktop app. |
| `resume_mcp` | MCP server so AI apps (e.g. Claude) can generate resumes: they get `success` / `failure: <reason>`, the file is written on your computer. |

The desktop app and the MCP server can run at the same time. Settings and the default format are cached locally and re-validated against the server, so they are not fetched on every use.

## Run

```bash
cp .env.example .env            # fill in MONGODB_URI and JWT_SECRET
python3 -m pip install -r requirements.txt
python -m resume_server         # the API
python -m resume_gui            # the desktop app (add --with-server to start a local API too)
python -m resume_mcp            # the MCP server (set RW_API_TOKEN, see docs)
```

See [docs/documentation.md](docs/documentation.md) for the full setup, `.env` reference and Claude Desktop configuration.

## Tests

```bash
python3 -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t .
```

## Releases

GitHub Actions on **`main`** runs tests always; when `HEAD` has a git tag equal to
`APP_VERSION` (`vX.Y.Z`), it also builds macOS/Windows PyInstaller zips and
publishes a GitHub Release. See [RELEASE.md](RELEASE.md) for the cut checklist
(`bump APP_VERSION` + tag `vX.Y.Z` when merging to `main`).

The UI uses explicitly styled plain Tk widgets instead of `ttk` because macOS's bundled Tk 8.5 can render `ttk` controls incorrectly in dark mode.

User documentation lives in [docs/documentation.md](docs/documentation.md) (and in Notion); it is not shown inside the app.
