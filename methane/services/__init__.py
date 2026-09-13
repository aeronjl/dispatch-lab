"""Composable field service models. Legacy field-operations/1 remains separately versioned."""

import hashlib
from pathlib import Path

CONTRACT_VERSION = "dispatch-lab/service-contracts/1"

# Bind standalone service evidence to the source present when this package loads.
# Whole-plant runs additionally capture the application and registered effect ports.
SOURCE_IDENTITY = {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(Path(__file__).parent.glob("*.py"))
}
