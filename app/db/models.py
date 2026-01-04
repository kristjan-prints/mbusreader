from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from typing import Any
from .database import Base
from .utc_types import UtcEpochSeconds, epoch_now


class MBusMeterData(Base):
    __tablename__ = "mbus_meter_data"

    timestamp: Mapped[int] = mapped_column(primary_key=True)
    mbus_slave_address: Mapped[int] = mapped_column(primary_key=True)
    meter_reading: Mapped[float] = mapped_column(nullable=False)


class Properties(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[int] = mapped_column(UtcEpochSeconds(), nullable=False, default=epoch_now)
    valid_till: Mapped[int | None] = mapped_column(UtcEpochSeconds(), nullable=True)

