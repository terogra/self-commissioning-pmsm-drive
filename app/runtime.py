"""Locate packaged resources without depending on the working directory."""

from pathlib import Path


def resource_root():
    # PyInstaller sets package __file__ inside its onedir _internal directory.
    # The same layout works in a source checkout, without a frozen-path branch.
    return Path(__file__).resolve().parents[1]


def dashboard_path():
    return resource_root()/"app/dashboard.py"
