# Resume Writer

A small Python desktop application that collects resume content and writes a `.docx` file locally.

## Features

- Tkinter desktop GUI with dropdowns for font, name size, heading size, and normal text size.
- Text boxes for Summary, Skills, Job Experience, Certifications, and Top 5 Skills.
- Job Experience accepts pasted lines such as `Company | January 2025 - May 2026`; dated lines are aligned left/right, and all other lines become bullets by default.
- The optional Certifications section is rendered after Education only when certification content is provided.
- In Job Experience bullet points only, spaced em-dash separators such as ` — ` are converted to `, `.
- Fixed education section and fixed header contact information from the base resume.
- Email and phone number hyperlinks in the generated Word file.
- Horizontal separator rules between resume sections.
- DOCX metadata:
  - Author: `Yashashchandra Kollu`
  - Subject: `my resume`
  - Keywords: first five skills from the Top 5 Skills input

## Run

```bash
python3 -m pip install -r requirements.txt
python3 resume_writer_app.py
```

The UI uses explicitly styled plain Tk widgets instead of `ttk` because macOS's bundled Tk 8.5 can render `ttk` controls incorrectly in dark mode.

The generated document uses the base resume's page geometry: US Letter with 0.75 inch margins and compact paragraph spacing. The default typeface is Arial, matching the base document defaults.
