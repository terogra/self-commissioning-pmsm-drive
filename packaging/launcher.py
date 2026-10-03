"""PyInstaller entry point; normal Python source entry stays python -m app."""

from app.portable import main

if __name__ == "__main__": raise SystemExit(main())
