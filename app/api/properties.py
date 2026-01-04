from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Properties
from app.db.utc_types import epoch_now
from app.security import require_token

from app.runtime_config import get_runtime_config, load_runtime_config

router = APIRouter(
    prefix="/properties",
    tags=["properties"],
    dependencies=[Depends(require_token)],
)

MBUS_SLAVE_KEY = "MBUS_SLAVE"

@router.get("/mbus-slaves")
def list_slaves():

    mbus_slaves = get_runtime_config().mbus_slaves

    return {
        "slaves": [
            {
                "address": slave.id,
                "name": slave.name,
                "valid_from": slave.valid_from
            }
            for slave in mbus_slaves
        ]
    }


class SlaveIn(BaseModel):
    name: str
    id: int = Field(ge=0, le=250)


@router.post("/mbus-slaves")
def add_slave(payload: SlaveIn, db: Session = Depends(get_db)):
    row = db.scalar(
        select(Properties)
        .where(
            and_(
                Properties.key == MBUS_SLAVE_KEY,
                Properties.valid_till.is_(None),
                Properties.value["id"].as_integer() == payload.id
            )
        )
        .order_by(Properties.id.desc())
    )

    if row:
        if payload.name != row.value["name"]:
            row.value = {
                "name": payload.name,
                "id": payload.id,
            }
            _commit_and_reload_runtime_config(db)

        return {
            "status": "ok",
            "addr": payload.id,
            "name": row.value["name"],
            "valid_from": row.valid_from,
        }

    row = Properties(
        key=MBUS_SLAVE_KEY,
        value={
            "name": payload.name,
            "id": payload.id,
        },
        valid_from=epoch_now(),
        valid_till=None,
    )
    db.add(row)
    _commit_and_reload_runtime_config(db)
    return {
        "status": "ok",
        "addr": payload.id,
        "name": row.value["name"],
        "valid_from": row.valid_from,
    }


@router.delete("/mbus-slaves/{id}")
def remove_slave(id: int, db: Session = Depends(get_db)):

    if id < 0 or id > 250:
        raise HTTPException(status_code=422, detail="M-Bus primary address must be in range 0..250")

    row = db.scalar(
        select(Properties)
        .where(
            and_(
                Properties.key == MBUS_SLAVE_KEY,
                Properties.valid_till.is_(None),
                Properties.value["id"].as_integer() == id
            )
        )
        .order_by(Properties.id.desc())
    )
    if not row:
        raise HTTPException(status_code=404, detail="Slave not found")

    row.valid_till = epoch_now()
    _commit_and_reload_runtime_config(db)

    return {"status": "ok", "id": id}


# Temporary endpoint to add/delete system properties
class SystemPropertyIn(BaseModel):
    key: str
    value: Any = None
    valid_from: int = Field(default_factory=epoch_now)
    valid_till: int | None = None


@router.post("/system-properties")
def add_system_property(payload: SystemPropertyIn, db: Session = Depends(get_db)):

    row = Properties(
        key=payload.key,
        value=payload.value,
        valid_from=payload.valid_from,
        valid_till=payload.valid_till
    )
    db.add(row)
    _commit_and_reload_runtime_config(db)

    return {
        "status": "ok",
        "key": row.key,
        "value": row.value,
        "valid_from": row.valid_from,
        "valid_till": row.valid_till
    }

@router.delete("/system-properties")
def remove_system_property(payload: SystemPropertyIn, db: Session = Depends(get_db)):

    row = db.scalar(
        select(Properties)
        .where(
            and_(
                Properties.key == payload.key,
                Properties.value == payload.value,
                Properties.valid_from == payload.valid_from,
                Properties.valid_till == payload.valid_till
            )
        )
        .order_by(Properties.id.desc())
    )
    if not row:
        raise HTTPException(status_code=404, detail="System property not found")

    row.valid_till = epoch_now()
    _commit_and_reload_runtime_config(db)

    return {"detail": "System property deleted"}


def _commit_and_reload_runtime_config(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    load_runtime_config()

