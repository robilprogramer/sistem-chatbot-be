
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from informasional.utils.db import Base


class StudentRegistration(Base):
    """Model untuk data pendaftaran siswa"""
    __tablename__ = "student_registrations"

    id = Column(Integer, primary_key=True, index=True)
    registration_number = Column(String(100), unique=True, nullable=False, index=True)
    
    # Data terstruktur dalam JSONB
    student_data = Column(JSONB, nullable=True)    # nama, alamat, dll
    parent_data = Column(JSONB, nullable=True)     # data orang tua
    academic_data = Column(JSONB, nullable=True)   # data akademik
    
    # Status
    status = Column(String(50), default="pending_payment", index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    documents = relationship("RegistrationDocument", back_populates="registration", cascade="all, delete-orphan")
    tracking = relationship("RegistrationTracking", back_populates="registration", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<StudentRegistration {self.registration_number}>"


class RegistrationDocument(Base):
    """Model untuk dokumen pendaftaran"""
    __tablename__ = "registration_documents"

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("student_registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    document_type = Column(String(50), nullable=False)  # foto, ijazah, akta, dll
    filename = Column(String(255), nullable=True)
    file_path = Column(Text, nullable=True)
    status = Column(String(50), default="uploaded")
    
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    registration = relationship("StudentRegistration", back_populates="documents")

    def __repr__(self):
        return f"<RegistrationDocument {self.document_type} - {self.filename}>"


class RegistrationTracking(Base):
    """Model untuk tracking status pendaftaran"""
    __tablename__ = "registration_tracking"

    id = Column(Integer, primary_key=True, index=True)
    registration_id = Column(Integer, ForeignKey("student_registrations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    status = Column(String(100), nullable=False)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    registration = relationship("StudentRegistration", back_populates="tracking")

    def __repr__(self):
        return f"<RegistrationTracking {self.status}>"