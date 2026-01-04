import math

import pytest
from pydantic import ValidationError

from app.api.mbus import MeterDataInsertItem
from app.db.models import MBusMeterData


def test_meter_data_request_model_rejects_non_finite_reading():
    with pytest.raises(ValidationError):
        MeterDataInsertItem(
            timestamp=1800000000,
            meter_reading=math.nan,
        )


def test_insert_meter_data_rejects_negative_reading(client, db_session):
    response = client.post(
        "/mbus/meter_data/insert",
        json={
            "slave_address": 220,
            "rows": [
                {
                    "timestamp": 1800000000,
                    "meter_reading": -1,
                }
            ],
        },
    )

    assert response.status_code == 422
    assert db_session.query(MBusMeterData).count() == 0


def test_update_meter_data_reports_replacement_counts_without_writing_on_dry_run(client, db_session):
    db_session.add_all(
        [
            MBusMeterData(
                timestamp=1800000000,
                mbus_slave_address=220,
                meter_reading=100.0,
            ),
            MBusMeterData(
                timestamp=1800000900,
                mbus_slave_address=220,
                meter_reading=101.0,
            ),
            MBusMeterData(
                timestamp=1800001800,
                mbus_slave_address=220,
                meter_reading=102.0,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        "/mbus/meter_data/update",
        json={
            "slave_address": 220,
            "start_timestamp": 1800000000,
            "end_timestamp": 1800003600,
            "dry_run": True,
            "rows": [
                {
                    "timestamp": 1800000000,
                    "meter_reading": 100.0,
                },
                {
                    "timestamp": 1800000900,
                    "meter_reading": 101.5,
                },
                {
                    "timestamp": 1800002700,
                    "meter_reading": 103.0,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "inserted": 1,
        "updated": 1,
        "deleted": 1,
        "unchanged": 1,
        "dry_run": True,
    }

    rows = {
        row.timestamp: row.meter_reading
        for row in db_session.query(MBusMeterData)
        .filter(MBusMeterData.mbus_slave_address == 220)
        .all()
    }
    assert rows == {
        1800000000: 100.0,
        1800000900: 101.0,
        1800001800: 102.0,
    }
