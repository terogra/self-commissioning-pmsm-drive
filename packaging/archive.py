"""Create the portable ZIP and SHA256SUMS only after a successful EXE smoke test."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


def create_archive(directory, output, version, smoke_result):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    if not json.loads(Path(smoke_result).read_text(encoding="utf-8"))["native_desktop_verified"]:
        raise ValueError("A successful packaged-EXE smoke test is required")
    if not (directory/"PMSM-Commissioning-Workbench.exe").is_file():
        raise FileNotFoundError("Missing portable executable")
    root = Path(__file__).resolve().parents[1]
    shutil.copy2(root/"LICENSE", directory/"LICENSE")
    shutil.copy2(root/"packaging/README_WINDOWS_TR.md", directory/"BASLANGIC_TR.md")
    shutil.copy2(root/"packaging/README_WINDOWS_EN.md", directory/"START_HERE_EN.md")
    (directory/"BUILD_INFO.json").write_text(json.dumps({"version": version,
        "source_commit": os.environ.get("GITHUB_SHA"), "build_workflow": os.environ.get("GITHUB_RUN_ID"),
        "unsigned": True}, indent=2)+"\n", encoding="utf-8")
    output.mkdir(parents=True, exist_ok=True)
    name = f"PMSM-Commissioning-Workbench-v{version}-Windows-x64"
    archive = Path(shutil.make_archive(str(output/name), "zip", root_dir=directory.parent, base_dir=directory.name))
    with archive.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    checksum = output/"SHA256SUMS.txt"
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(checksum.read_text(), end="")
    return archive, checksum


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--smoke-result", type=Path, required=True)
    args = parser.parse_args()
    create_archive(args.directory, args.output, args.version, args.smoke_result)
