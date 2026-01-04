from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from app.db.database import get_db
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, FiniteFloat

from app.security import require_token
from app.db.queries import get_meter_data, insert_meter_data, delete_meter_data, update_meter_data
from app.constants import DEFAULT_TRANSFER_LIMIT


router = APIRouter(
    prefix="/mbus",
    tags=["mbus"],
    dependencies=[Depends(require_token)],
)


class MeterDataRequest(BaseModel):
    slave_address: int
    start_after_timestamp: int = 0          # Last saved record's timestamp. Value will be 0 if none.
    end_timestamp: Optional[int] = None
    limit: int = Field(default=DEFAULT_TRANSFER_LIMIT, ge=1, le=30000)


class MeterDataInsertItem(BaseModel):
    timestamp: int = Field(ge=0)
    meter_reading: FiniteFloat = Field(ge=0)


class MeterDataInsertRequest(BaseModel):
    slave_address: int
    rows: list[MeterDataInsertItem] = Field(min_length=1, max_length=5000)
    overwrite_existing: bool = False


class MeterDataInsertResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int


class MeterDataDeleteRequest(BaseModel):
    slave_address: int
    timestamps: list[int] = Field(min_length=1, max_length=5000)


class MeterDataDeleteResponse(BaseModel):
    deleted: int


class MeterDataUpdateRequest(BaseModel):
    slave_address: int
    start_timestamp: int
    end_timestamp: int
    dry_run: bool = True
    rows: list[MeterDataInsertItem] = Field(default_factory=list, max_length=5000)


class MeterDataUpdateResponse(BaseModel):
    inserted: int
    updated: int
    deleted: int
    unchanged: int
    dry_run: bool


# # #
# Example payload for send_meter_data endpoint:
#
# {
#     "slave_address": 210,
#     "start_after_timestamp": 1774744200
#     "end_timestamp" : 1774749600
# }
# # #
@router.post("/meter_data")
def send_meter_data(payload: MeterDataRequest, db: Session = Depends(get_db)):

    rows = get_meter_data(
        db=db, 
        mbus_slave_address=payload.slave_address, 
        start_after_timestamp=payload.start_after_timestamp, 
        end_timestamp=payload.end_timestamp, 
        limit=payload.limit
    )

    return [
        {
            "timestamp": r.timestamp,
            "mbus_slave_address": r.mbus_slave_address,
            "meter_reading": r.meter_reading,
        }
        for r in rows
    ]

# # #
# Example payload for insert_meter_data_endpoint:
#
# {
#   "slave_address": 200,
#   "overwrite_existing": false,
#   "rows": [
#     {"timestamp": 1774746000, "meter_reading": 12345.67},
#     {"timestamp": 1774746900, "meter_reading": 12346.12}
#   ]
# }
# # #
@router.post("/meter_data/insert", response_model=MeterDataInsertResponse)
def insert_meter_data_endpoint(payload: MeterDataInsertRequest, db: Session = Depends(get_db)):
    # optional safety: quarter-hour alignment
    bad_timestamps = [row.timestamp for row in payload.rows if row.timestamp % 900 != 0]
    if bad_timestamps:
        raise HTTPException(
            status_code=422,
            detail=f"timestamps must be 15-minute aligned; bad values: {bad_timestamps}",
        )

    result = insert_meter_data(
        db=db,
        slave_address=payload.slave_address,
        rows=[(row.timestamp, row.meter_reading) for row in payload.rows],
        overwrite_existing=payload.overwrite_existing,
    )
    return result


@router.delete("/meter_data", response_model=MeterDataDeleteResponse)
def delete_meter_data_endpoint(payload: MeterDataDeleteRequest, db: Session = Depends(get_db)):

    deleted = delete_meter_data(
        db=db,
        slave_address=payload.slave_address,
        timestamps=payload.timestamps,
    )
    return {"deleted": deleted}


# # #
# Example payload for update_meter_data_endpoint:
#
# {
#   "slave_address": 200,
#   "start_timestamp": 1774746000,
#   "end_timestamp": 1774749600,
#   "dry_run": true,
#   "rows": [
#     {
#       "timestamp": 1774746000,
#       "meter_reading": 12345.67
#     },
#     {
#       "timestamp": 1774746900,
#       "meter_reading": 12346.12
#     },
#     {
#       "timestamp": 1774747800,
#       "meter_reading": 12346.58
#     }
#   ]
# }
# # #
@router.post("/meter_data/update", response_model=MeterDataUpdateResponse)
def update_meter_data_endpoint(payload: MeterDataUpdateRequest, db: Session = Depends(get_db)):
    if payload.start_timestamp >= payload.end_timestamp:
        raise HTTPException(status_code=422, detail="start_timestamp must be < end_timestamp")

    bad_timestamps = [
        row.timestamp
        for row in payload.rows
        if row.timestamp % 900 != 0
    ]
    if bad_timestamps:
        raise HTTPException(
            status_code=422,
            detail=f"timestamps must be 15-minute aligned; bad values: {bad_timestamps}",
        )

    out_of_range = [
        row.timestamp
        for row in payload.rows
        if not (payload.start_timestamp <= row.timestamp < payload.end_timestamp)
    ]
    if out_of_range:
        raise HTTPException(
            status_code=422,
            detail=f"rows outside requested range: {out_of_range}",
        )

    return update_meter_data(
        db=db,
        slave_address=payload.slave_address,
        start_timestamp=payload.start_timestamp,
        end_timestamp=payload.end_timestamp,
        rows=[(row.timestamp, row.meter_reading) for row in payload.rows],
        dry_run=payload.dry_run,
    )
