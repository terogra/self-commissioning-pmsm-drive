"""Check packaged Qt startup and clean process shutdown."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import time


def smoke_test(executable, output, timeout=45):
    executable, output = Path(executable).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output/"qt_startup.json"
    report_path.unlink(missing_ok=True)
    started = time.monotonic()
    process = None
    failure = None
    native = {}
    subsystem = None
    workspace = tempfile.TemporaryDirectory(prefix="pmsm unrelated cwd ")
    try:
        if os.name == "nt":
            binary = executable.read_bytes()
            pe_offset = struct.unpack_from("<I", binary, 0x3c)[0]
            subsystem = struct.unpack_from("<H", binary, pe_offset+24+68)[0]
            if subsystem != 2: raise RuntimeError("EXE is not a windowed Windows GUI executable")
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
            environment.pop(key, None)
        with (output/"stdout.log").open("w", encoding="utf-8") as out, (output/"stderr.log").open("w", encoding="utf-8") as err:
            process = subprocess.Popen([str(executable), "--smoke-report", str(report_path)],
                cwd=workspace.name, env=environment, stdout=out, stderr=err)
            process.wait(timeout=timeout)
        if process.returncode != 0: raise RuntimeError(f"Native executable exited with {process.returncode}")
        native = json.loads(report_path.read_text(encoding="utf-8"))
        if not all(native.get(name) for name in ("qt_window_initialized", "window_visible", "frozen")):
            raise RuntimeError("Actual packaged Qt window was not initialized")
        if native.get("qt_platform") != "offscreen" or native.get("forbidden_runtime_modules") != []:
            raise RuntimeError("Unexpected Qt platform or web runtime dependency")
        print(f"Native packaged Qt window initialized; clean exit; {time.monotonic()-started:.3f} s", flush=True)
    except Exception as exc:
        failure = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        workspace.cleanup()
        report = {"native_desktop_verified": failure is None, "elapsed_s": time.monotonic()-started,
            "exit_code": None if process is None else process.returncode, "failure": failure,
            "executable": str(executable), "windows_pe_subsystem": subsystem, "qt": native}
        (output/"smoke_result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        if failure:
            print("NATIVE SMOKE FAILURE:", failure, flush=True)
            for path in (output/"stdout.log", output/"stderr.log"):
                content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else "(not created)"
                print(path.name+":\n"+content, flush=True)
            raise RuntimeError(failure)
    return report


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    smoke_test(args.exe, args.output)
