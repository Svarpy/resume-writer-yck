# Changelog

> **Source of truth (Sprint 1):** This changelog has been migrated to the Notion teamspace **resume-writer-yck**.
> Maintain updates on the Notion page: https://app.notion.com/p/3e0bfc4f45de80e38d83c7db6005af1e
> This local file is retained pending Project Lead / PM approval to delete.

## Unreleased

### v4 (v4generic)

- Removed the in-app updater completely (the weekly GitHub Releases check, the Install Now / Remind Later dialog, the Updates settings, `resume_gui/update/` and its tests). Releases are still built by CI; the app no longer checks for or installs them.
- **Architecture rewrite.** The application is split into `resume_core` (engine), `resume_server` (FastAPI + MongoDB), `resume_client` (API client, local cache, local generation), `resume_gui` (Tk app) and `resume_mcp` (MCP server). The old `resume_writer` package, the root compatibility shims and every local JSON/XML data file are gone.
- **MongoDB** now stores accounts, access tokens, format metadata, the uploaded sample documents and settings. Secrets live in `.env` (see `.env.example`); only the server needs them. Existing local data is not migrated: sign up again and re-upload formats.
- The database is `resume-writer`; its `system` collection records every app version with the newest marked `latest` (`current_version`, `latest_version`, `versions`), updated when the server starts and readable at `GET /api/v1/system`.
- Uploaded samples are stored **sanitised** (the author's name, contact details, employers and text are replaced by placeholders; formatting is unchanged, output is identical). Generated resumes no longer carry the sample's old email/phone hyperlink targets.
- Parser/generator hardening from a 47-format resume corpus: contact details spread over several lines or separated by line breaks, label|value skill tables, dates in parentheses or after `|` / `,` keep the sample's punctuation, date-first lines (`2021 – Present  Company`), numbered or colon headings, case-insensitive header/footer scrubbing, education detected by degree/institution wording when the heading is unusual.
- **Download Backup** (a button pinned to the bottom of the Settings page's left list, **administrators only**): download a `mongodump`-style zip of the whole database named `ResWritBkpYYYYMMMDD.zip` to the local computer. Users have a `role` (`user` by default, set to `admin` by hand in MongoDB); for other roles the option is not shown and the API answers a plain 404 Not Found.
- API documentation: Swagger UI at `/docs` (ReDoc at `/redoc`) now has an Authorize button for access/login tokens and grouped endpoints; Profile > Access Tokens has an **Open API Documentation** button. Backup endpoints are not listed.
- **FastAPI interface** with JWT login and personal access tokens, per-user isolation, and a `/state` endpoint for cache validation.
- **MCP server** (`python -m resume_mcp`): generate resumes, check duplicates, manage formats and settings from AI apps. Documents are written on the local computer; the AI app only receives `success` / `failure: <reason>`.
- **Local cache** for settings, the default format and its sample, invalidated by revision numbers; shared by the desktop app and the MCP server; works offline for generation.
- The desktop app and MCP server can run at the same time; Profile gained Access Tokens.
- The desktop bundle is built without server code, database drivers or secrets.

- Settings are now a per-user, JSON-backed page (`settings.json`) grouped alphabetically by category, with search, per-setting reset, a modified marker and a raw JSON editor. Added: Appearance, Duplicate Check, Education, Experience Parsing, Fonts, Metadata, Output, Personal Details, Resume Sections, Updates, Validation, Writer.
- Resume Sections are fully dynamic: add, rename, reorder, hide and set the heading, kind, width and word limits. The Writer page builds its text boxes from them and the DOCX renders them in that order.
- Profile (account details and password) moved from Settings to a Profile page above Sign Out in the sidebar; the collapsed sidebar shows a person icon (letter `P` as fallback).
- Removed the Documentation page, the Help > Usage Help item and the bundled `documentation.md`; the documentation now lives in `docs/documentation.md` and Notion.
- Hard-coded personal data (name, contact details, education, company date defaults, output folder, `YcKResume` file prefix) moved into Settings; defaults are generic. The header and education editors left the Writer page.
- Duplicate check can be switched off and its folders and file types configured; checking no longer creates the `#applied` folder.
- Required fields are chosen in Settings > Validation (including File Name); section word limits are per section.
- New OOXML parser replaces the old Formatter extraction. A sample `.docx` is analysed for header, sections and line exemplars, and generation clones the sample's own XML with the new text, so output matches the sample (page setup, styles, numbering, tables, multi-column skills, run formatting) for any content. Works for table-based and unusual layouts.
- Resume Sections, Fonts and Required Fields are now stored per resume format; choosing a format in the Formatter switches them.
- Settings: saves while typing, scrolls with the mouse anywhere, accepts hex/RGB/HSL/named colours, hides rarely used options behind Show Advanced, one accent colour. Fixed highlighted labels after switching theme.
- Personal Details gained an optional Tagline.
- Fixed: `October` (and other months containing `to`) was mangled by date normalisation.
- Removed the built-in default resume format and the old python-docx layout builder. A user uploads a sample on first use; it becomes the default format, and the default can be changed (Formatter: Make Default). Deleting the default promotes another one. The Writer asks for an upload until a format exists.
- The Writer's font and size dropdowns now apply on top of the sample only where they differ from it.
- Sign-in: Enter now submits the form (it used to move to the next field), and the username and password stay filled after Sign Out; the username is also remembered between launches (the password is never written to disk).
- Fixed: Settings did not scroll with a trackpad/mouse unless the pointer was on the scrollbar (Tk 9 sends trackpad scrolling as a separate event).
- Fixed: the default (non-template) format dropped DOCX author/subject/keywords metadata; the README author mismatch; leftover dead code in `render/models.py`; missing `ResumeFormat` import in the Writer.
- Breaking: default output folder is now `~/Documents/Resumes` and the default file name is `Resume{company}{date}`; set Output settings to restore a previous folder or prefix.

- Pre–Sprint 2 package layout refactor (structure/hygiene only): application code under `resume_writer/` with layer rule `ui` → `render` → `formats` → `auth` → `paths`; thin `resume_writer_app.py` / `python -m resume_writer` entrypoints and root compat shims; unittest suite under `tests/` via `python -m unittest discover -s tests`.
- Release pipeline (Sprint 2): `APP_VERSION` + tag `vX.Y.Z` on `main` publishes `ResumeWritervX.Y.Z.app.zip` / `.exe.zip`; unsigned builds (Gatekeeper / SmartScreen note). Operator checklist: `RELEASE.md`.

## v3.0.0

- App version shown as v3.0.0 in the window title and About dialog.
- Signup confirm-password live match feedback; Sign Out returns to a cleared Sign In page.
- Sidebar shows display name (falls back to username); Formatter no longer offers Update on saved formats.

## v2.1

- Updated Job Experience fallback dates and preserved pasted dates before applying company-aware fallback defaults.
- Stabilized dated resume rows with fixed-width left/right columns instead of spacing-based alignment.
- Fixed submit shortcuts from text fields and added folder/name-based output validation with case-insensitive duplicate checks.
- Refined output filename entry sizing and extended duplicate checks into the `#applied` folder.
- Added filename status markers and clear the filename field after generation while preserving the last output path.

## v2.0

- Added keyboard navigation and submission shortcuts.
- Added validation for required fields and 41-50 word summaries.
- Added editable header and selectable/editable education entries.
- Added light/dark mode and About menu details.
- Refined the dark/light toggle, moved Header And Education below Output, and moved validation guidance into Help.
- Updated app version to v2.0.0, refined dark colors, replaced native-painted controls, and balanced reduced-window field resizing.
- Improved button contrast and disabled/enabled hover cursors.
- Preserved pasted job dates before applying fallback role date defaults.

## v1.1

- Added Aptos to the font dropdown.
- Changed the default output folder to `/Users/yck/Desktop/CLGENAPPL`.
- Changed the default filename format to `YcKResumeXXXDDMMM.docx`.
