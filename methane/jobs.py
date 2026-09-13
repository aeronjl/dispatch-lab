"""Bounded subprocess execution keeps batch numerical work outside the UI interpreter."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def isolated_run(config, weather, cancelled=None, progress=None, strategies=None):
    with tempfile.TemporaryDirectory(prefix="dispatch-batch-") as directory:
        root = Path(directory)
        (root / "input.json").write_text(
            json.dumps(
                {"config": config.to_dict(), "weather": weather, "strategies": strategies},
                allow_nan=False,
            )
        )
        env = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "DISPATCH_BATCH_WORKER": "1",
        }
        with (root / "worker.log").open("w") as log:
            worker = subprocess.Popen(
                [sys.executable, "-m", "methane.batch_worker", str(root)],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
            )
            last = None
            cancel_started = None
            try:
                while worker.poll() is None:
                    if cancelled and cancelled():
                        (root / "cancel").touch()
                        cancel_started = cancel_started or time.monotonic()
                        if time.monotonic() - cancel_started > 15:
                            worker.terminate()
                            raise RuntimeError(
                                "Batch worker did not acknowledge cancellation within 15 seconds"
                            )
                    if progress and (root / "progress.json").exists():
                        message = (root / "progress.json").read_text()
                        if message != last:
                            data = json.loads(message)
                            progress(data["fraction"], desc=data["description"])
                            last = message
                    time.sleep(0.05)
                if worker.returncode:
                    if (root / "error.json").exists():
                        error = json.loads((root / "error.json").read_text())
                        raise RuntimeError(error["type"] + ": " + error["message"])
                    raise RuntimeError(
                        "Batch worker failed: " + (root / "worker.log").read_text()[-2000:]
                    )
                result = json.loads((root / "result.json").read_text())
                return result
            finally:
                if worker.poll() is None:
                    worker.terminate()
                    try:
                        worker.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        worker.kill()
                        worker.wait()
