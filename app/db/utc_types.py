from datetime import timezone, datetime, UTC
from sqlalchemy import types


def utcnow() -> datetime:
    return datetime.now(UTC)

def epoch_now() -> int:
    return int(utcnow().timestamp())

def epoch_floor_to_15_minutes(ts: int) -> int:
    return ts - (ts % 900)

def to_epoch_minute(date_time: datetime) -> int:
    # Ensure timezone-aware
    if date_time.tzinfo is None:
        date_time = date_time.replace(tzinfo=timezone.utc)

    truncated = date_time.replace(second=0, microsecond=0)
    return int(truncated.timestamp())


class UtcEpochSeconds(types.TypeDecorator):
    """
    Stores datetimes as INTEGER seconds since Unix epoch (UTC).
    Returns timezone-aware UTC datetime objects on read.
    """
    impl = types.BigInteger # Configuration hook for SQLAlchemy
    cache_ok = True         # Configuration hook for SQLAlchemy

    def process_bind_param(self, value, dialect):
        if value is None:
            return None

        # Allow passing an int directly (already epoch ms)
        if isinstance(value, int):
            return value

        if not isinstance(value, datetime):
            raise TypeError(f"UtcEpochSeconds expects datetime or int, got {type(value)}")

        if value.tzinfo is None:
            raise ValueError("Naive datetime is not allowed. Provide a timezone-aware datetime (UTC).")

        return int(value.astimezone(timezone.utc).timestamp())

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc)
