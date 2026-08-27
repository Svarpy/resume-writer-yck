# Resume Writer Documentation

Version: v2.0

Resume Writer is a desktop application for creating a formatted `.docx` resume from user-provided content. It is designed to keep the resume format consistent while allowing the main content, header details, education selections, certifications, and output file path to be edited from the app.

## Contents

- [What The Application Includes](#what-the-application-includes)
- [Generated Resume Behavior](#generated-resume-behavior)
- [Required Fields And Validation](#required-fields-and-validation)
- [Keyboard Support](#keyboard-support)
- [How To Use The Application](#how-to-use-the-application)
- [Job Experience Input Tips](#job-experience-input-tips)
- [Mac Installation](#mac-installation)
- [Windows Installation](#windows-installation)
- [Updating Dependencies](#updating-dependencies)
- [Security Notes](#security-notes)
- [Troubleshooting](#troubleshooting)

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
- Output file picker with a default save location.
- Help menu with usage guidance.
- About menu with application name and current version.

## Generated Resume Behavior

The app generates a local Word document in `.docx` format.

- Default output folder:
  `/Users/yck/Desktop/CLGENAPPL`
- Default file name format:
  `YcKResumeXXXDDMMM.docx`
- `XXX` is the company placeholder.
- `DD` is the current day.
- `MMM` is the current month abbreviation, such as `Jul`, `Aug`, or `Sep`.

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
9. Review the output file path.
10. Replace `XXX` in the file name with the target company name.
11. Edit the header fields if needed.
12. Select Masters and/or Bachelors in the education section.
13. Edit education details if needed by clicking the edit symbol.
14. Click Generate DOCX.

After the file is generated successfully, the app clears the content input fields so the next resume can be started cleanly.

## Job Experience Input Tips

Use one item per line.

For company or role lines with dates, use one of these formats:

```text
First Horizon Bank | Atlanta, GA | January 2025 - May 2026
Software Engineer - Full Stack | January 2025 - May 2026
```

The app aligns the left side and date side in the generated document.

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
python resume_writer_app.py
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

### Dates In Job Experience Look Wrong

Use a clear date format on company or role lines:

```text
Company Name | Location | January 2025 - May 2026
Role Name | January 2025 - May 2026
```

Pasted dates should be preserved. Fallback dates are only used when a known company or role line does not include a date.
