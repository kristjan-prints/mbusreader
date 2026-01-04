import logging
from typing import cast
from collections.abc import Sequence
from sqlalchemy import and_, or_, select, delete
from sqlalchemy.orm import Session

from app.db.utc_types import epoch_now
from app.db.models import Properties, MBusMeterData
from app.constants import DEFAULT_TRANSFER_LIMIT

log = logging.getLogger("mbusreader.db")


def get_active_properties(db: Session, key: str, ts: int | None = None) -> list[Properties]:
    ts = epoch_now() if ts is None else ts

    rows = db.scalars(
        select(Properties)
        .where(
            and_(
                Properties.key == key,
                Properties.valid_from <= ts,
                or_(
                    Properties.valid_till.is_(None),
                    Properties.valid_till > ts,
                ),
            )
        )
        .order_by(Properties.valid_from.asc())
    ).all()

    return cast(list[Properties], rows)


def get_last_meter_reading(db: Session, mbus_slave_address: int) -> float | None:
    try:
        value = db.scalars(
            select(MBusMeterData.meter_reading)
            .where(MBusMeterData.mbus_slave_address == mbus_slave_address)
            .order_by(MBusMeterData.timestamp.desc())
            .limit(1)
        ).first()
        return value
    except Exception as e:
        log.error("Failed to read last meter_reading for slave %s: %s", mbus_slave_address, e, exc_info=True)
        return None
    
# # # 

def get_meter_data(*, db: Session, mbus_slave_address: int, start_after_timestamp: int, end_timestamp: int | None = None, limit: int = DEFAULT_TRANSFER_LIMIT) -> Sequence[MBusMeterData]:

    if end_timestamp is None:
        end_timestamp = epoch_now()

    try:
        rows = (
            db.execute(
                select(MBusMeterData)
                .where(
                    and_(
                        MBusMeterData.mbus_slave_address == mbus_slave_address,
                        MBusMeterData.timestamp > start_after_timestamp,
                        MBusMeterData.timestamp <= end_timestamp
                    )
                )
                .order_by(MBusMeterData.timestamp.asc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return rows
    except Exception as e:
        log.error(
            "Failed to read meter data for slave %s from %s to %s: %s",
            mbus_slave_address,
            start_after_timestamp,
            end_timestamp,
            e,
            exc_info=True,
        )
        return []


def insert_meter_data(db: Session, slave_address: int, rows: Sequence[tuple[int, float]], overwrite_existing: bool = False) -> dict[str, int]:
    # de-duplicate payload by timestamp; last value wins
    normalized: dict[int, float] = {}
    for timestamp, meter_reading in rows:
        normalized[timestamp] = meter_reading

    if not normalized:
        return {"inserted": 0, "updated": 0, "skipped": 0}

    timestamps = sorted(normalized.keys())

    existing_rows = db.scalars(
        select(MBusMeterData).where(
            MBusMeterData.mbus_slave_address == slave_address,
            MBusMeterData.timestamp.in_(timestamps),
        )
    ).all()

    existing_by_timestamp = {row.timestamp: row for row in existing_rows}

    inserted = 0
    updated = 0
    skipped = 0

    try:
        for timestamp in timestamps:
            meter_reading = normalized[timestamp]
            existing = existing_by_timestamp.get(timestamp)

            if existing is None:
                db.add(
                    MBusMeterData(
                        timestamp=timestamp,
                        mbus_slave_address=slave_address,
                        meter_reading=meter_reading,
                    )
                )
                inserted += 1
                continue

            if overwrite_existing and existing.meter_reading != meter_reading:
                existing.meter_reading = meter_reading
                updated += 1
            else:
                skipped += 1

        if inserted or updated:
            db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


def delete_meter_data(db: Session, slave_address: int, timestamps: list[int]) -> int:
    unique_timestamps = sorted(set(timestamps))

    if not unique_timestamps:
        return 0

    stmt = delete(MBusMeterData).where(
        MBusMeterData.mbus_slave_address == slave_address,
        MBusMeterData.timestamp.in_(unique_timestamps),
    )

    result = db.execute(stmt)
    db.commit()

    return max(result.rowcount, 0)


def update_meter_data(
    db: Session,
    slave_address: int,
    start_timestamp: int,
    end_timestamp: int,
    rows: Sequence[tuple[int, float]],
    dry_run: bool = True,
) -> dict[str, int]:
    normalized: dict[int, float] = {}
    for timestamp, meter_reading in rows:
        normalized[timestamp] = meter_reading

    existing_rows = db.scalars(
        select(MBusMeterData).where(
            and_(
                MBusMeterData.mbus_slave_address == slave_address,
                MBusMeterData.timestamp >= start_timestamp,
                MBusMeterData.timestamp < end_timestamp,
            )
        )
    ).all()

    existing_by_timestamp = {row.timestamp: row for row in existing_rows}
    incoming_timestamps = set(normalized.keys())

    to_insert: list[dict[str, float | int]] = []
    to_update: list[dict[str, float | int]] = []
    unchanged = 0

    for timestamp, meter_reading in normalized.items():
        existing = existing_by_timestamp.get(timestamp)

        if existing is None:
            to_insert.append(
                {
                    "timestamp": timestamp,
                    "mbus_slave_address": slave_address,
                    "meter_reading": meter_reading,
                }
            )
        elif existing.meter_reading != meter_reading:
            to_update.append(
                {
                    "timestamp": timestamp,
                    "mbus_slave_address": slave_address,
                    "meter_reading": meter_reading,
                }
            )
        else:
            unchanged += 1

    timestamps_to_delete = [
        row.timestamp
        for row in existing_rows
        if row.timestamp not in incoming_timestamps
    ]

    inserted = len(to_insert)
    updated = len(to_update)
    deleted = len(timestamps_to_delete)

    if dry_run:
        return {
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
            "dry_run": dry_run,
        }

    try:
        if to_insert:
            db.bulk_insert_mappings(MBusMeterData, to_insert)

        if to_update:
            db.bulk_update_mappings(MBusMeterData, to_update)

        if timestamps_to_delete:
            db.execute(
                delete(MBusMeterData).where(
                    MBusMeterData.mbus_slave_address == slave_address,
                    MBusMeterData.timestamp.in_(timestamps_to_delete),
                )
            )

        if inserted or updated or deleted:
            db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted,
        "unchanged": unchanged,
        "dry_run": dry_run,
    }
