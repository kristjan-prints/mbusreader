from __future__ import annotations

import os
import logging
import time
from typing import Any

import serial
import meterbus
import json
import math
from app.db.utc_types import utcnow, epoch_floor_to_15_minutes
from app.db.database import SessionLocal
from app.db.models import MBusMeterData
from app.db.queries import get_last_meter_reading
from app.runtime_config import get_runtime_config
from app.scheduler.syncer import trigger_sync_job


log = logging.getLogger("mbusreader.scheduler")


def scheduled_task_of_fetching_kwh_data_from_mbus() -> None:

    cfg = get_runtime_config()

    try:
        run_time = utcnow()
        timestamp = epoch_floor_to_15_minutes(int(run_time.timestamp()))

        log.info("Scheduled task of fetching kWh data from M-Bus triggered @ %s",run_time.isoformat())

        MBR_SERIAL_DEV = os.getenv("MBR_SERIAL_DEV", "/dev/ttyAMA4")
        MBR_BAUD_RATE = int(os.getenv("MBR_BAUD_RATE", "9600"))

        mbus_slaves = cfg.mbus_slaves

        with SessionLocal() as db:
            log.info("Number of M-Bus slaves:  %s", len(mbus_slaves))

            try:
                with serial.Serial(MBR_SERIAL_DEV, MBR_BAUD_RATE, 8, 'E', 1, 0.5) as ser:
                    for slave in mbus_slaves:
                        log.info("Reading Power Meter's data from M-Bus slave address %s (%s) ...", slave.id, slave.name)

                        try:
                            kwh_data = read_data_from_mbus_slave(ser, slave.id)

                            current_meter_reading = read_current_meter_reading_from_data_record(kwh_data)

                            if current_meter_reading is None:
                                log.warning("No valid current meter reading extracted from data of M-Bus slave address %s", slave.id)
                                continue

                            last_meter_reading = get_last_meter_reading(db, slave.id)

                            # last_meter_reading could be None and nothing bad will happen
                            if current_meter_reading == last_meter_reading:
                                log.info("Current meter reading is the same as last meter reading for M-Bus slave address %s and this reading will not be saved.", slave.id)
                                continue

                            # Save new meter reading
                            new_meter_data_record = MBusMeterData(
                                timestamp=timestamp,
                                mbus_slave_address=slave.id,
                                meter_reading=current_meter_reading
                            )
                            db.add(new_meter_data_record)

                        except (serial.SerialException, serial.SerialTimeoutException) as e:
                            log.error("Serial error reading slave %s: %s", slave.id, e, exc_info=True)
                        except json.JSONDecodeError as e:
                            log.error("Invalid JSON from slave %s: %s", slave.id, e, exc_info=True)
                        except Exception as e:
                            log.error("Error reading slave %s: %s", slave.id, e, exc_info=True)

            except (serial.SerialException, serial.SerialTimeoutException) as e:
                log.error("Serial port error (%s @ %s): %s", MBR_SERIAL_DEV, MBR_BAUD_RATE, e, exc_info=True)
                return

            if db.new:
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    log.error("Commit failed", exc_info=True)
                    raise
    finally:
        try:
            if cfg.has_upload_server:
                trigger_sync_job(cfg.sync_delay_seconds)
        except Exception:
            log.error("Failed to trigger sync job", exc_info=True)


def read_data_from_mbus_slave(ser: serial.Serial, mbus_slave_address: int) -> dict[str, Any]:

    for attempt in range(3):
        try:
            meterbus.send_ping_frame(ser, mbus_slave_address)
            frame = meterbus.load(meterbus.recv_frame(ser, 1))
            if not isinstance(frame, meterbus.TelegramACK):
                raise ValueError(f"Expected ACK, got {type(frame).__name__}")

            meterbus.send_request_frame(ser, mbus_slave_address)
            frame = meterbus.load(meterbus.recv_frame(ser, meterbus.FRAME_DATA_LENGTH))
            if not isinstance(frame, meterbus.TelegramLong):
                raise ValueError(f"Expected TelegramLong, got {type(frame).__name__}")

            raw_kwh_data = frame.to_JSON()
            log.info("Raw kWh data read from M-Bus slave address %s @ %s", mbus_slave_address, utcnow().isoformat())
            return json.loads(raw_kwh_data)

        except meterbus.MBusFrameDecodeError as exc:
            if "empty frame" not in str(exc) or attempt == 2:
                raise
            log.warning("M-Bus frame was empty for slave %s, retrying: %s", mbus_slave_address, exc)
            ser.reset_input_buffer()
            time.sleep(1)


def read_current_meter_reading_from_data_record(data_rec: dict[str, Any]) -> float | None:

    records = data_rec.get("body", {}).get("records", [])
    if not isinstance(records, list):
        log.warning("Unexpected records structure")
        return None

    rec = next(
        (
            r for r in records
            if isinstance(r, dict)
            and r.get("function") == str(meterbus.FunctionType.INSTANTANEOUS_VALUE)
            and r.get("type") == str(meterbus.VIFUnit.ENERGY_WH)
            and r.get("unit") == str(meterbus.MeasureUnit.WH)
            and "tariff" not in r
            and isinstance(r.get("value"), (int, float))
            and not math.isinf(r["value"])
            and not math.isnan(r["value"])
        ),
        None,
    )

    if rec is None:
        log.warning("No valid total ENERGY_WH instantaneous record found")
        return None

    return rec["value"] / 1000.0    # convert Wh to kWh

