"""Start the actual packaged EXE from an unrelated directory and require HTTP 200.

All failures print exit code, stdout, stderr and listening-port diagnostics.
No browser opens; no installed Python/Git is used by the child executable.
"""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.error import URLError


def smoke_test(executable, output, port=18511, timeout=45):
    executable, output = Path(executable).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stdout, stderr = output/"stdout.log", output/"stderr.log"
    started = time.monotonic()
    process = None
    success = False
    failure = None
    workspace = None
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # fail before launch if the test port is occupied
        environment = dict(os.environ, PMSM_HEADLESS="1", PMSM_PORT=str(port))
        for key in ("PYTHONPATH", "PYTHONHOME"):
            environment.pop(key, None)
        workspace = tempfile.TemporaryDirectory(prefix="pmsm unrelated cwd ")
        with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen([str(executable)], cwd=workspace.name, env=environment,
                stdout=out, stderr=err, creationflags=flags)
            while time.monotonic()-started < timeout:
                if process.poll() is not None:
                    raise RuntimeError("Packaged executable exited before readiness")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as response:
                        healthy = response.status == 200
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=1) as response:
                        body = response.read().decode("utf-8")
                        success = healthy and response.status == 200 and "streamlit" in body.lower()
                    if success:
                        if process.poll() is not None:
                            raise RuntimeError("Executable exited after HTTP response")
                        break
                except (URLError, TimeoutError, OSError):
                    pass
                time.sleep(.2)
            if not success:
                raise RuntimeError(f"No HTTP 200 readiness within {timeout} s")
            print(f"Packaged EXE HTTP 200: 127.0.0.1:{port}; ready in {time.monotonic()-started:.3f} s", flush=True)
            # A hidden Windows test process has no interactive console for
            # Ctrl+C. It has no spawned Python child; terminate then wait.
            process.terminate()
            process.wait(timeout=10)
    except Exception as exc:
        failure = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        # Kill/wait MUST precede removal of a Windows process's locked cwd.
        if workspace is not None:
            try:
                workspace.cleanup()
            except OSError as exc:
                failure = (failure+"; " if failure else "")+f"Temporary directory cleanup failed: {exc}"
        report = {"http_200": success and failure is None, "port": port, "loopback": "127.0.0.1",
            "elapsed_s": time.monotonic()-started, "exit_code_after_cleanup": None if process is None else process.returncode,
            "failure": failure, "executable": str(executable)}
        (output/"smoke_result.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        if failure:
            print("SMOKE FAILURE:", failure, flush=True)
            print("Process exit code:", report["exit_code_after_cleanup"], flush=True)
            for name, path in (("stdout", stdout), ("stderr", stderr)):
                print(f"--- {name} ---\n{path.read_text(encoding='utf-8', errors='replace') if path.exists() else '(not created)'}", flush=True)
            if os.name == "nt":
                ports = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
                print("Relevant listening ports:\n"+"\n".join(line for line in ports.splitlines()
                    if "LISTENING" in line and (f":{port} " in line or ":8501 " in line)), flush=True)
            raise RuntimeError(failure)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18511)
    args = parser.parse_args()
    smoke_test(args.exe, args.output, args.port)
