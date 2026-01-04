import os
import logging
from typing import Any
import requests
from datetime import datetime, timedelta, UTC

from collections.abc import Sequence

from app.db.database import SessionLocal
from app.db.queries import get_meter_data
from app.db.utc_types import utcnow
from app.runtime_config import MBusSlave, UploadServer, get_runtime_config
from app.scheduler.instance import scheduler
from app.db.models import MBusMeterData
from app.constants import DEFAULT_TRANSFER_LIMIT

log = logging.getLogger("mbusreader.sync")


def trigger_sync_job(delay: int) -> None:
    scheduler.add_job(
        sync_with_rpp,
        trigger="date",
        run_date=datetime.now(UTC) + timedelta(seconds=delay),
        id="sync_with_rpp",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )


def sync_with_rpp() -> None:
    try:
        cfg = get_runtime_config()
        if cfg.upload_server is None:
            return

        client_cert = (
            os.environ["M2M_CLIENT_CERT"],
            os.environ["M2M_CLIENT_KEY"],
        )

        with requests.Session() as session:

            last_records = _get_last_records_from_rpp(
                session=session,
                device_id=cfg.device_identity.id,
                mbus_slaves=cfg.mbus_slaves,
                upload_server=cfg.upload_server,
                client_cert=client_cert
            )

            with SessionLocal() as db:
                for slave in cfg.mbus_slaves:
                    slave_address = slave.id
                    last_ts = last_records.get(str(slave_address))
                    if last_ts is None:
                        log.info("No last timestamp for slave %s from RPP, fetching all data up to now", slave_address)
                        last_ts = 0

                    while meter_data := get_meter_data(db=db, mbus_slave_address=slave_address, start_after_timestamp=last_ts):

                        _upload_meter_data_to_rpp(
                            session=session,
                            device_id=cfg.device_identity.id,
                            slave_address=slave_address,
                            meter_data=meter_data,
                            upload_server=cfg.upload_server,
                            client_cert=client_cert
                        )

                        # Following part will update the last_ts and go for another loop if len(meter_data) = DEFAULT_TRANSFER_LIMIT. More items expected in next batch.
                        if len(meter_data) < DEFAULT_TRANSFER_LIMIT:
                            break

                        last_ts = meter_data[-1].timestamp

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        log.warning("Sync with RPP skipped: RPP unreachable: %s", e)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        log.warning("Sync with RPP failed: HTTP %s: %s", status, e)

    except requests.exceptions.RequestException as e:
        log.warning("Sync with RPP failed: request error: %s", e)

    except Exception:
        log.exception("Unexpected sync with RPP failure")


def _get_last_records_from_rpp(*, session: requests.Session, device_id: int, mbus_slaves: list[MBusSlave], upload_server: UploadServer, client_cert: tuple[str, str]) -> dict[str, int | None]:

    payload = {
        "device_id": device_id,
        "meter_addresses": [slave.id for slave in mbus_slaves],
    }

    sync_url = upload_server.base_url.rstrip("/") + "/api/m2m/sync"

    response = session.post(
        sync_url,
        json=payload,
        cert=client_cert,
        verify=upload_server.verify,
        timeout=(5, 30),
    )
    response.raise_for_status()

    return response.json().get("last_records", {})


def _upload_meter_data_to_rpp(
        *, 
        session: requests.Session,
        device_id: int, 
        slave_address: int, 
        meter_data: Sequence[MBusMeterData], 
        upload_server: UploadServer, 
        client_cert: tuple[str, str]
) -> dict[str, int]:

    payload = {
        "device_id": device_id,
        "meter_address": slave_address,
        "meter_data": [
            {
                "timestamp": r.timestamp,
                "meter_reading": r.meter_reading,
            }
            for r in meter_data
        ]
    }

    sync_url = upload_server.base_url.rstrip("/") + "/api/m2m/meter-data"

    response = session.post(
        sync_url,
        json=payload,
        cert=client_cert,
        verify=upload_server.verify,
        timeout=(5, 30),
    )
    response.raise_for_status()

    return response.json()

