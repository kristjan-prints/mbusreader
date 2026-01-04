from app.db.models import MBusMeterData
from app.db.utc_types import epoch_now
from app.runtime_config import DeviceIdentity, MBusSlave, RuntimeConfig, UploadServer
from app.scheduler.syncer import sync_with_rpp
import app.scheduler.syncer as syncer_module


class ResponseStub:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class SessionStub:
    def __init__(self, last_timestamp):
        self.posts = []
        self.last_timestamp = last_timestamp

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/api/m2m/sync"):
            return ResponseStub({"last_records": {"220": self.last_timestamp}})
        return ResponseStub({"saved_count": len(kwargs["json"]["meter_data"])})


def test_sync_uploads_only_rows_after_rpp_last_timestamp(db_session, monkeypatch):
    now = epoch_now()
    old_timestamp = now - 2700
    last_timestamp = now - 1800
    unsynced_timestamp = now - 900

    db_session.add_all(
        [
            MBusMeterData(
                timestamp=old_timestamp,
                mbus_slave_address=220,
                meter_reading=99.0,
            ),
            MBusMeterData(
                timestamp=last_timestamp,
                mbus_slave_address=220,
                meter_reading=100.0,
            ),
            MBusMeterData(
                timestamp=unsynced_timestamp,
                mbus_slave_address=220,
                meter_reading=101.0,
            ),
        ]
    )
    db_session.commit()

    cfg = RuntimeConfig(
        device_identity=DeviceIdentity(name="reader", id=1001),
        upload_server=UploadServer(base_url="https://rpp.example", verify=True),
        mbus_slaves=[MBusSlave(name="main", id=220, valid_from=0)],
        sync_delay_seconds=10,
    )
    session = SessionStub(last_timestamp)

    class SessionFactory:
        def __call__(self):
            return db_session

    class RequestsSessionFactory:
        def __call__(self):
            return session

    monkeypatch.setattr(syncer_module, "get_runtime_config", lambda: cfg)
    monkeypatch.setattr(syncer_module, "SessionLocal", SessionFactory())
    monkeypatch.setattr(syncer_module.requests, "Session", RequestsSessionFactory())
    monkeypatch.setenv("M2M_CLIENT_CERT", "/tmp/client.crt")
    monkeypatch.setenv("M2M_CLIENT_KEY", "/tmp/client.key")

    sync_with_rpp()

    upload_posts = [
        kwargs["json"]
        for url, kwargs in session.posts
        if url.endswith("/api/m2m/meter-data")
    ]

    assert upload_posts == [
        {
            "device_id": 1001,
            "meter_address": 220,
            "meter_data": [
                {
                    "timestamp": unsynced_timestamp,
                    "meter_reading": 101.0,
                }
            ],
        }
    ]
