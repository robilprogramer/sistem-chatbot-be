from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from informasional.utils.db import Base


class MasterCabangModel(Base):
    __tablename__ = "master_cabang"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(100), nullable=False, unique=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
