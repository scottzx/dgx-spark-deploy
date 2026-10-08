#!/usr/bin/env python3
"""Start an isolated SGLang benchmark and restore the previously running idle LLM."""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request


ROOT = Path("/home/admin/qwen-image-2.1-runtime")
CONTAINER = "qwen3-8-flash-next"


def health(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    output = ROOT / "outputs" / time.strftime("sglang-speed-%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    (ROOT / "latest-sglang-speed-dir.txt").write_text(str(output) + "\n")
    locks = []
    for path in (ROOT / "inference.lock", Path("/home/admin/sol-spark-runtime/inference.lock")):
        handle = path.open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 30010))
    previous = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}"], text=True).splitlines()
    paused = False
    server = None
    receipt = {"source_commit": "5828cd49276a419402b316aec0236e5c2161e46d", "status": "starting"}
    try:
        if CONTAINER in previous:
            with urllib.request.urlopen("http://127.0.0.1:8001/slots", timeout=5) as response:
                slots = json.load(response)
            if not slots or not all(s.get("is_processing") is False for s in slots):
                raise RuntimeError("Language model has active requests")
            paused = True
            subprocess.run(["docker", "stop", "--timeout", "60", CONTAINER], check=True)
        processes = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"], text=True).strip()
        if processes:
            raise RuntimeError(f"Other GPU work is active: {processes}")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "sglang-test/python"),
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CUDA_VISIBLE_DEVICES="0", PYTHONUNBUFFERED="1",
                   CUDA_HOME="/usr/local/cuda",
                   CPATH="/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include")
        env["PATH"] = str(ROOT / "sglang-venv/bin") + ":/usr/local/cuda/bin:" + os.environ.get("PATH", "")
        python = str(ROOT / "sglang-venv/bin/python")
        command = [str(ROOT / "sglang-venv/bin/sglang"), "serve", "--model-path", "/home/admin/models_cache/Qwen-Image-2.1",
                   "--model-id", "Qwen-Image-2.1", "--performance-mode", "speed", "--attention-backend", "torch_sdpa",
                   "--backend", "sglang", "--host", "127.0.0.1", "--port", "30010"]
        receipt["command"] = command
        start = time.monotonic()
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        while not health("http://127.0.0.1:30010/health"):
            if server.poll() is not None:
                raise RuntimeError(f"Server exited with {server.returncode}; see server.log")
            if time.monotonic() - start > 900:
                raise TimeoutError("Server did not become healthy within 900 seconds")
            time.sleep(2)
        receipt["startup_seconds"] = time.monotonic() - start
        print(json.dumps(receipt), flush=True)
        subprocess.run([python, str(ROOT / "benchmark_qwen_image_21_http.py"),
                        "--cases-dir", str(ROOT / "outputs/acceptance-20260929-164210"),
                        "--output", str(output / "images")], check=True, env=env)
        receipt["status"] = "passed_structural_checks_pending_visual_review"
    except BaseException as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
        raise
    finally:
        if server is not None:
            try:
                os.killpg(server.pid, signal.SIGTERM)
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=10)
            except ProcessLookupError:
                pass
        if paused:
            subprocess.run(["docker", "start", CONTAINER], check=True)
            deadline = time.monotonic() + 180
            while not health("http://127.0.0.1:8001/health") and time.monotonic() < deadline:
                time.sleep(2)
            receipt["language_model_restored"] = health("http://127.0.0.1:8001/health")
        (output / "run.json").write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt), flush=True)
        if paused and not receipt.get("language_model_restored"):
            raise RuntimeError("Language model restart did not become healthy")


if __name__ == "__main__":
    main()
