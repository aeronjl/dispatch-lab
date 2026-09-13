"""Cache explicitly selected public evidence; retain errors and content hashes."""

import argparse
import datetime
import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fetch(name, url):
    target = HERE / "raw" / name
    manifest_path = HERE / "downloads.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if target.exists() and name in manifest and manifest[name].get("status") == "downloaded":
        print(name, "cached", target.stat().st_size)
        return
    entry = {"url": url, "retrieved_utc": datetime.datetime.now(datetime.UTC).isoformat()}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "DispatchLabResearch/1.0"}),
            timeout=45,
        ) as response:
            data = response.read()
            target.write_bytes(data)
            entry.update(
                status="downloaded",
                final_url=response.url,
                content_type=response.headers.get("Content-Type"),
                bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
        print(name, len(data), entry["content_type"])
    except Exception as error:
        entry.update(status="failed", error=str(error))
        print(name, "FAILED", str(error))
    manifest[name] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("url", nargs="?")
    args = parser.parse_args()
    if args.url:
        fetch(args.name, args.url)
    else:
        for name, url in json.loads((HERE / args.name).read_text()).items():
            fetch(name, url)
