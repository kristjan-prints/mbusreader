from app.db.models import Properties
from app.db.queries import get_active_properties
from app.db.utc_types import epoch_now
from app.runtime_config import get_runtime_config, load_runtime_config
import app.runtime_config as runtime_config_module


def test_active_properties_excludes_future_and_expired_rows(db_session):
    db_session.add_all(
        [
            Properties(
                key="MBUS_SLAVE",
                value={"name": "expired", "id": 210},
                valid_from=1000,
                valid_till=1500,
            ),
            Properties(
                key="MBUS_SLAVE",
                value={"name": "current", "id": 211},
                valid_from=1500,
                valid_till=None,
            ),
            Properties(
                key="MBUS_SLAVE",
                value={"name": "future", "id": 212},
                valid_from=2500,
                valid_till=None,
            ),
        ]
    )
    db_session.commit()

    rows = get_active_properties(db_session, "MBUS_SLAVE", ts=2000)

    assert [row.value["name"] for row in rows] == ["current"]


def test_runtime_config_uses_current_device_id_not_future_one(db_session, monkeypatch):
    now = epoch_now()

    db_session.add_all(
        [
            Properties(
                key="DEVICE_ID",
                value={"name": "current-device", "id": 1001},
                valid_from=now - 100,
                valid_till=None,
            ),
            Properties(
                key="DEVICE_ID",
                value={"name": "future-device", "id": 1002},
                valid_from=now + 100,
                valid_till=None,
            ),
        ]
    )
    db_session.commit()

    class SessionFactory:
        def __call__(self):
            return db_session

    monkeypatch.setattr(runtime_config_module, "SessionLocal", SessionFactory())
    monkeypatch.setattr(runtime_config_module, "runtime_config", None)
    load_runtime_config()

    cfg = get_runtime_config()

    assert cfg.device_identity.name == "current-device"
    assert cfg.device_identity.id == 1001
