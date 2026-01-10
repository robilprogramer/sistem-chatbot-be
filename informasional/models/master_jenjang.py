from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from informasional.utils.db import Base


class MasterJenjangModel(Base):
    __tablename__ = "master_jenjang"

    id = Column(Integer, primary_key=True, index=True)
    kode = Column(String(50), nullable=False, unique=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
