"""python -m resume_writer entrypoint."""

from __future__ import annotations

import os

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


def main() -> None:
    # Temporary: full UI still lives in the monolith until the UI move step.
    from resume_writer_app import ResumeWriterApp

    ResumeWriterApp().mainloop()


if __name__ == "__main__":
    main()
