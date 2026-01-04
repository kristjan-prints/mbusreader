from dataclasses import dataclass
import os

from app.db.database import SessionLocal
from app.db.queries import get_active_properties


@dataclass(slots=True, frozen=True)
class DeviceIdentity:
    name: str
    id: int


@dataclass(slots=True, frozen=True)
class UploadServer:
    base_url: str
    verify: str | bool


@dataclass(slots=True, frozen=True)
class MBusSlave:
    name: str
    id: int
    valid_from: int


@dataclass(slots=True, frozen=True)
class RuntimeConfig:
    device_identity: DeviceIdentity
    upload_server: UploadServer | None
    mbus_slaves: list[MBusSlave]
    sync_delay_seconds: int

    @property
    def has_upload_server(self) -> bool:
        return self.upload_server is not None


runtime_config: RuntimeConfig | None = None


def load_runtime_config() -> None:
    global runtime_config

    DELAY_SECONDS = int(os.getenv("SYNC_DELAY_SECONDS", 10))

    with SessionLocal() as db:
        device_row = get_active_properties(db, "DEVICE_ID")
        if not device_row or len(device_row) != 1:
            raise RuntimeError("DEVICE_ID is missing or misconfigured.")
        device_row = device_row[0]

        upload_server_rows = get_active_properties(db, "UPLOAD_SERVER")
        upload_server = None
        if upload_server_rows:
            row = upload_server_rows[0]
            upload_server = UploadServer(
                base_url=row.value["baseUrl"],
                verify=row.value["verify"],
            )

        mbus_slave_rows = get_active_properties(db, "MBUS_SLAVE")

        runtime_config = RuntimeConfig(
            device_identity=DeviceIdentity(
                name=device_row.value["name"],
                id=int(device_row.value["id"]),
            ),
            upload_server=upload_server,
            mbus_slaves=[
                MBusSlave(
                    name=row.value["name"],
                    id=int(row.value["id"]),
                    valid_from=row.valid_from
                )
                for row in mbus_slave_rows
            ],
            sync_delay_seconds=DELAY_SECONDS
        )


def get_runtime_config() -> RuntimeConfig:
    if runtime_config is None:
        raise RuntimeError("Runtime config is not loaded")
    return runtime_config

