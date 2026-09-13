"""Subprocess helpers that never flash a console window on Windows.

When the parent has no visible console (``pythonw`` app, test runner, agent),
Windows gives each console child process its own console window that briefly
pops up and closes.  Setting ``CREATE_NO_WINDOW`` suppresses it.  Route every
``git`` / ``gh`` / ``ncm-cli`` call through here instead of ``subprocess``
directly.
"""
import subprocess
import sys

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _apply(kwargs):
    if sys.platform == "win32" and _CREATE_NO_WINDOW:
        kwargs.setdefault("creationflags", _CREATE_NO_WINDOW)
    return kwargs


def run(args, **kwargs):
    """``subprocess.run`` with a hidden console window on Windows."""
    return subprocess.run(args, **_apply(kwargs))


def popen(args, **kwargs):
    """``subprocess.Popen`` with a hidden console window on Windows."""
    return subprocess.Popen(args, **_apply(kwargs))
