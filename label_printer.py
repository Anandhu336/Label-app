#!/usr/bin/env python3
# label_printer.py

import os
import sys
import glob
import subprocess
from typing import List, Tuple


def list_label_files(label_dir: str) -> List[str]:
    """
    Return a sorted list of PNG label files in the given directory.

    Files are sorted numerically if the filename (without extension)
    is an integer (e.g. 1.png, 2.png, 10.png). Others fall back to
    alphabetical order after numeric ones.
    """
    pattern = os.path.join(label_dir, "*.png")
    files = glob.glob(pattern)

    def sort_key(path: str):
        name = os.path.basename(path)
        base, _ = os.path.splitext(name)
        # Try numeric sort first
        try:
            num = int(base)
            # (0, num) ensures all numeric names come first,
            # and are sorted by integer value
            return (0, num)
        except ValueError:
            # Non-numeric names go after, sorted alphabetically
            return (1, base.lower())

    files.sort(key=sort_key)
    return files


def open_label_externally(path: str) -> Tuple[bool, str | None]:
    """
    Open the given image file in the system's default viewer.

    The user can then print from that viewer (Cmd+P / Ctrl+P).
    Returns (success: bool, error_message: str | None).
    """
    try:
        if sys.platform.startswith("darwin"):
            # macOS
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("win"):
            # Windows
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform.startswith("linux"):
            # Linux
            subprocess.Popen(["xdg-open", path])
        else:
            return False, f"Unsupported platform: {sys.platform}"

        return True, None
    except Exception as e:
        return False, str(e)


def _print_single_file(path: str) -> Tuple[bool, str | None]:
    """
    Send a single file to the default printer, OS-specific.
    Returns (success, error_message).
    """
    try:
        if sys.platform.startswith("darwin"):
            # macOS: use lpr
            subprocess.run(["lpr", path], check=False)
        elif sys.platform.startswith("win"):
            # Windows: use the 'print' verb
            # This sends to default printer configured in Windows
            os.startfile(path, "print")  # type: ignore[attr-defined]
        elif sys.platform.startswith("linux"):
            # Linux: lp or lpr (here using lp)
            subprocess.run(["lp", path], check=False)
        else:
            return False, f"Unsupported platform: {sys.platform}"

        return True, None
    except Exception as e:
        return False, str(e)


def print_all_labels(label_dir: str) -> Tuple[int, int, List[str]]:
    """
    Print ALL label PNGs in the provided directory.

    Returns:
      (success_count, fail_count, errors)
    """
    files = list_label_files(label_dir)
    success_count = 0
    fail_count = 0
    errors: List[str] = []

    for f in files:
        ok, err = _print_single_file(f)
        if ok:
            success_count += 1
        else:
            fail_count += 1
            if err:
                errors.append(f"{os.path.basename(f)}: {err}")

    return success_count, fail_count, errors