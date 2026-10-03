"""Legacy development-only web UI. Primary product: python -m desktop."""

from pathlib import Path
import subprocess
import sys


def launch_command(arguments=()):
    script = Path(__file__).resolve().with_name("dashboard.py")
    return [sys.executable, "-m", "streamlit", "run", str(script),
        "--server.address=127.0.0.1", "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal", *arguments]


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        return subprocess.call(launch_command(sys.argv[1:]), cwd=root)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__": raise SystemExit(main())
