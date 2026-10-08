#!/usr/bin/env python3
"""Download official ModelScope files in resumable ranges, with SHA-256 verification."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.parse
import urllib.request


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(8 * 1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--repo", default="Qwen/Qwen-Image-2.1")
    args = parser.parse_args()
    entries = [f for f in json.loads(args.manifest.read_text())["Data"]["Files"] if f["Type"] == "blob"]
    jobs = []
    pending = []
    chunk_size = 64 * 1024 * 1024
    for item in entries:
        target = args.model / item["Path"]
        if not target.resolve().is_relative_to(args.model.resolve()):
            raise ValueError("Invalid manifest path")
        if target.exists() and target.stat().st_size == item["Size"] and sha256(target) == item["Sha256"]:
            print("Already verified", item["Path"], flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        parts = args.model / ".range-parts" / item["Sha256"]
        parts.mkdir(parents=True, exist_ok=True)
        url = ("https://modelscope.cn/models/" + args.repo + "/resolve/" +
               item["Revision"] + "/" + urllib.parse.quote(item["Path"]))
        for start in range(0, item["Size"], chunk_size):
            end = min(start + chunk_size, item["Size"]) - 1
            jobs.append((url, start, end, item["Size"], parts / str(start)))
        pending.append((item, target, parts))

    def download(job):
        url, start, end, total, part = job
        expected = end - start + 1
        if part.exists() and part.stat().st_size == expected:
            return expected
        for attempt in range(5):
            try:
                temporary = part.with_suffix(".partial")
                offset = temporary.stat().st_size if temporary.exists() else 0
                if offset > expected:
                    raise ValueError(f"Oversized partial file: {temporary}")
                if offset == expected:
                    temporary.replace(part)
                    return expected
                while offset < expected:
                    request_start = start + offset
                    # Keep individual transfers short enough for the origin's
                    # connection deadline, while preserving 64 MiB resume files.
                    request_end = min(request_start + 8 * 1024 * 1024 - 1, end)
                    request = urllib.request.Request(url, headers={"Range": f"bytes={request_start}-{request_end}"})
                    with urllib.request.urlopen(request, timeout=90) as response:
                        content_range = response.headers.get("Content-Range")
                        # The direct storage path sometimes returns HTTP 200
                        # with a correct Content-Range. Check the range and size.
                        if response.status in (200, 206) and content_range:
                            if content_range != f"bytes {request_start}-{request_end}/{total}":
                                raise ValueError(f"Unexpected Content-Range: {content_range}")
                            content_length = response.headers.get("Content-Length")
                            if content_length and int(content_length) != request_end - request_start + 1:
                                raise ValueError("Incorrect range Content-Length")
                        elif response.status != 200 or request_start != 0 or request_end + 1 != total:
                            raise ValueError("Server did not honor requested range")
                        with temporary.open("ab") as out:
                            shutil.copyfileobj(response, out, 1024 * 1024)
                    offset = temporary.stat().st_size
                    if offset != request_end - start + 1:
                        raise ValueError("Incomplete range")
                temporary.replace(part)
                return expected
            except Exception as error:
                print(f"Retry {attempt + 1}/5: {part}: {error}", flush=True)
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)

    started = time.monotonic()
    received = 0
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            try:
                received += future.result()
            except Exception as error:
                errors.append(str(error))
                print(f"Failed range: {error}", flush=True)
            print(f"Ranges {index}/{len(jobs)}; {received / 1e9:.2f} GB; {received / 1e6 / (time.monotonic() - started):.1f} MB/s", flush=True)
    if errors:
        raise RuntimeError(f"{len(errors)} ranges failed; rerun to resume: {errors}")
    for item, target, parts in pending:
        temporary = target.with_suffix(target.suffix + ".assembling")
        with temporary.open("wb") as out:
            for start in range(0, item["Size"], chunk_size):
                with (parts / str(start)).open("rb") as stream:
                    shutil.copyfileobj(stream, out, 8 * 1024 * 1024)
        if sha256(temporary) != item["Sha256"]:
            raise ValueError(f"SHA-256 mismatch: {target}")
        temporary.replace(target)
        shutil.rmtree(parts)
        print("Verified", item["Path"], flush=True)
    print("DOWNLOAD COMPLETE: all manifest files verified", flush=True)


if __name__ == "__main__":
    main()
