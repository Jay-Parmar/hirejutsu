"""Open files and links with the user's own programs."""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def edit_file(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        subprocess.run(f'{editor} "{path}"', shell=True)
    elif sys.platform == "win32":
        subprocess.run(["notepad", str(path)])
    elif sys.platform == "darwin":
        subprocess.run(["open", "-t", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


def open_url(url: str) -> None:
    webbrowser.open(url)
