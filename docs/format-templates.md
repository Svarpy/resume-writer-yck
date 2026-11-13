# Resume format templates

A *format* in Resume Writer is an ordinary Word document in which everything specific to one person has been replaced by
`{{placeholders}}`. The app never guesses what a line means: the template says so. Generation copies the template and
fills the placeholders, so the output looks exactly like the template.

You can make a template by hand in Word, or ask an AI tool to turn any sample resume into one (prompt at the end of this page).
Upload it in the **Formatter** (**Add Format**). To change a format later, press **Download**, edit the `.docx` in Word and
press **Replace File** (same entry, same default status, your settings are kept).

## Fields

| Placeholder | Meaning |
| --- | --- |
| `{{name}}` `{{tagline}}` `{{email}}` `{{phone}}` `{{location}}` | personal details (Settings > Personal Details) |
| `{{text}}` | the text of a paragraph section (a summary) or of a list item |
| `{{label}}` `{{values}}` | a skills line ``Label: values`` |
| `{{company}}` `{{location}}` `{{dates}}` | a job (inside `{{#jobs}}`) |
| `{{title}}` `{{dates}}` | a role (inside `{{#roles}}`) |
| `{{degree}}` `{{major}}` `{{institution}}` `{{location}}` `{{dates}}` `{{grade}}` | a degree (inside `{{#degrees}}`) |

Inside a block a field is looked up from the innermost block outwards, so `{{company}}` inside `roles` is the enclosing job's
company. `{{location}}` outside every block is your location; inside `degrees` it is the institution's.

## Blocks

`{{#x}}` starts and `{{/x}}` ends a block. The paragraphs or table rows between them are repeated once per item (and left out
when there is none). Put the start marker at the start of the first paragraph (or first table cell) of the block and the end
marker at the end of its last paragraph. A block may start or end between two rows of one table (the table is split there).

* **Sections**: every section is a top-level block named `summary`, `skills`, `experience`, `education`, `certifications`, ... A section
  with no content disappears together with its heading and the rule/spacer paragraph that opens it (put the section's start marker in
  that rule paragraph).
* **Inside a section**: `{{text}}` (paragraph) · `{{#items}}{{text}}{{/items}}` (list) · `{{#items}}{{label}}: {{values}}{{/items}}` (skills) ·
  `{{#jobs}}...{{#roles}}...{{#bullets}}{{text}}{{/bullets}}...{{/roles}}...{{/jobs}}` (experience) · `{{#degrees}}...{{/degrees}}` (education).
* **Merged lines**: if company and role share one line (`Title @ Company | dates`) put it inside `roles`.
* **Section kinds** are read from the content: `jobs` means experience, `degrees` education, `items` with `label`/`values` skills.

## Empty fields

An empty field disappears together with the fixed text that only introduced it: the separator before it (`" | "`, `", "`)
and a label (`"GPA: "`). A paragraph or table row whose fields are all empty is dropped; a blank spacer paragraph that ends a
repeated unit is not written after the last one.

## Handled by the app

Hyperlinks (email and phone become `mailto:` / `tel:` links), document properties, the file name, and the font and sizes chosen
in the Writer are applied by the app. Headings can be renamed or hidden in Settings > Resume Sections; the order of sections and their
layout come from the template. A field that the template does not contain is ignored (a template without dates in Education
prints none).

## What is checked at upload

Unbalanced or overlapping markers, unknown field or block names, fields outside a block, markers split over several runs
(these are repaired), and leftovers such as an email address. Every problem is listed so you can fix the template.

## Prompt for an AI tool

Give this prompt, together with your sample resume (.docx), to an AI tool that can edit Word files (for example Claude with
code execution). It is also available in the app: **Formatter > Copy AI Prompt**.

```text
You convert a sample resume (.docx) into a "Resume Writer format template": the SAME Word document with
all person-specific text replaced by placeholders. Layout, fonts, sizes, colours, spacing, tabs, tables,
borders, bullets/numbering, page setup and styles must stay exactly as in the sample. You change TEXT only.

HOW TO WORK
- Edit the .docx in place with python-docx / raw OOXML. Never rebuild or retype the document. Do not
  touch the original: save the result as "<original name>_TEMPLATE.docx".
- A placeholder is typed like {{name}} inside ONE run. One placeholder or one block marker per run and
  nothing else in that run. The run keeps the formatting of the sample text it replaces (bold, italic,
  size, colour, underline, font). A placeholder takes the formatting of the FIRST run of the text it
  replaces; do not reproduce partial bold/italic inside it.
- Fixed text (separators such as " | ", " – ", ", ", "@", labels such as "Education:" or "GPA:", headings)
  stays unchanged in its own runs. Keep tabs and line breaks where they are. Delete the other runs of the
  text you replaced.
- Keep the ORDER of fields and the literal text exactly as in the sample (e.g. "{{company}} {{title}}" vs
  "{{title}} @ {{company}}"). Never reorder or "improve" it.
- If something fits no rule, keep the sample's formatting, use the closest field, and say so in the REPORT.

FIELDS (use only these)
Top of the document: {{name}} {{tagline}} {{email}} {{phone}} {{location}}
Inside blocks (below): {{text}} {{label}} {{values}} {{company}} {{location}} {{title}} {{dates}}
{{degree}} {{major}} {{institution}} {{grade}}
- {{dates}} is the whole range as ONE placeholder (e.g. "June 2026 – Present"). Never split a date.
- Use only fields the sample really has (do not add {{dates}} to Education if it shows no dates).
- If the name, title and contact details share one paragraph, still use {{name}} / {{tagline}} / {{email}} ...
  in separate runs, keeping the sample's separators.

BLOCKS
- {{#x}} starts and {{/x}} ends a repeatable block. Type {{#x}} at the START of the first paragraph (or
  first cell of the first table row) of the block and {{/x}} at the END of its last paragraph (or last cell
  of its last row). The block covers everything in between. If both markers are in the same paragraph,
  that paragraph repeats. A table row repeats when the markers are in its first and last cell. A block may
  start or end between two rows of one table. Never add new paragraphs just for markers. Blocks may nest
  but never overlap.
- SECTIONS: wrap every section, from its first paragraph to its last content paragraph, in a block.
  Section names: summary, skills, experience, education, certifications, projects, awards when the heading
  means that (e.g. "WORK EXPERIENCE" / "PROFESSIONAL EXPERIENCE" -> experience); otherwise the heading in
  lowercase snake_case. Keep the heading text as written. A section without a heading (a summary directly
  under the contact line, an inline "Education: ..." line) is still wrapped, without heading text.
- A decorative rule or spacer paragraph that sits directly BEFORE a section heading belongs to that
  section: put the section's {{#x}} start marker at the start of that rule/spacer paragraph, not in the
  heading paragraph. Repeatable units (jobs, roles, bullets, items, degrees) must never start or end in
  such a rule, except as below.
- A blank spacer paragraph that ends a unit may carry that unit's {{/x}} end marker; the app does not emit
  it after the last repetition.
- Inside a section, by content type:
  * single paragraph:        {{text}}
  * list of lines/bullets:   {{#items}}{{text}}{{/items}}   (all in the one bullet paragraph)
  * skills "Label: values":  {{#items}}{{label}}: {{values}}{{/items}}   (label and values in separate
                             runs, each keeping its own bold/plain formatting)
  * skills without "Label:" (plain comma list or lines): {{#items}}{{text}}{{/items}}
  * skills in a table (label | values): the table row repeats: {{#items}} in the first cell with
                             {{label}}, {{values}} in the last cell with {{/items}}
  * wrapped continuation lines of ONE logical item (the same skill line broken over two paragraphs):
                             merge them into the one item paragraph
  * experience:              {{#jobs}} job line(s) {{#roles}} role line(s) {{#bullets}}{{text}}{{/bullets}}
                             {{/roles}} {{/jobs}}
      job fields {{company}} {{location}} {{dates}}; role fields {{title}} {{dates}}.
      If company and role share one line ("Title @ Company | dates"), put that line inside roles:
      "{{title}} @ {{company}} | {{dates}}" (roles may use the enclosing job's company/location/dates).
      If the sample has no separate role line (company line, then bullets), omit roles and put
      {{#bullets}} directly inside jobs.
  * education:               {{#degrees}} {{degree}} {{major}} {{institution}} {{location}} {{dates}}
                             {{grade}} {{/degrees}} (only the parts the sample has, each in its own run,
                             separators and labels unchanged)
  * any other list section (certifications, projects, awards, languages, ...): {{#items}}{{text}}{{/items}},
                             or, if the sample shows a title and dates per entry,
                             {{#items}}{{title}} {{dates}} {{text}}{{/items}}

REPETITION
Keep exactly ONE unit per repeatable level: the most complete example (all optional parts present) of a
job, of a role, one bullet paragraph, one skill line, one degree. Delete all other sample repetitions.
A blank spacer paragraph between units belongs inside the block, at its end.

OPTIONAL PARTS
Any field may be empty when generating. The app then drops the field together with all literal text
between the previous placeholder and that field (separator and label, e.g. "  |  GPA: "). Keep a label in
the same literal run directly before its field, and do not add anything else for optional parts.

HANDLED BY THE APP - DO NOT PUT THESE IN THE TEMPLATE
- Hyperlinks: remove every hyperlink element (w:hyperlink) and delete its relationship. Keep the run
  formatting (colour, underline) exactly as the sample shows it on the {{email}} / {{phone}} runs. The app
  creates mailto:/tel: links from its settings.
- Document properties (author, title, subject, keywords, description, last-modified-by): empty them.
- File name, dates of creation: not your concern.
- Headers/footers: delete any personal data; use placeholders only if the sample shows name/contact there.

TEXT WITH NO PLACEHOLDER
Person-specific text with no field in this list (e.g. "Environment: ..." lines, references, photos, other
links): if it is a list-like section, make it a section block with {{#items}}{{text}}{{/items}};
otherwise delete the paragraph.

SELF-CHECK BEFORE ANSWERING
1. Every {{#x}} has a matching {{/x}}; blocks are nested properly and none overlap.
2. No leftover personal text anywhere in the package (document, headers, footers, properties,
   relationship files): names, companies, schools, dates, emails, phones, URLs, cities, bullets.
3. Each placeholder or marker sits alone in a single run.
4. For each placeholder run, paragraph and run properties equal those of the sample text it replaced
   (compare the XML). Bullet numbering is unchanged (numId was not changed or set to 0).
5. No unit block (jobs, roles, bullets, items, degrees) starts or ends in a rule paragraph; each section's
   rule/spacer paragraph that precedes its heading carries that section's start marker.
6. No w:hyperlink elements and no hyperlink relationships remain.
7. The file opens; page size, margins, styles and numbering definitions are untouched.

OUTPUT
The .docx, then a REPORT with:
(1) the block outline, indented, for example:
      summary > text
      skills > items(label, values)
      experience > jobs(company, location, dates) > roles(title, dates) > bullets(text)
      education > degrees(degree, major, institution, dates)
(2) the sections found and their type,
(3) anything you deleted or were unsure about.
```
