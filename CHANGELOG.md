# Changelog

> **Source of truth (Sprint 1):** This changelog has been migrated to the Notion teamspace **resume-writer-yck**.
> Maintain updates on the Notion page: https://app.notion.com/p/3e0bfc4f45de80e38d83c7db6005af1e
> This local file is retained pending Project Lead / PM approval to delete.

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
