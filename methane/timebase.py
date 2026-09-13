"""UTC interval convention, independent of any provider or network transport."""

from datetime import UTC, datetime


def utc(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def stamp(d):
    return d.astimezone(UTC).isoformat()
