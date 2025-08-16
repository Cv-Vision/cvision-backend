import uuid
from sqlalchemy import create_engine, Column, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

# This is the base class from which all our models will inherit.
# It allows SQLAlchemy to map the classes to the database tables.
Base = declarative_base()

class JobPosting(Base):
    """
    Represents the 'job_postings' table in the database.
    """
    __tablename__ = 'job_postings'

    # --- Columns ---
    posting_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_user_id = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    location = Column(String(100))
    experience_level = Column(String(50))
    english_level = Column(String(50))
    contract_type = Column(String(50))
    industry_experience = Column(JSON)
    additional_requirements = Column(JSON)
    status = Column(String(50), default='ACTIVE')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    # This creates a link to the JobApplication model.
    # The 'back_populates' argument links it back to the 'job_posting' attribute
    # in the JobApplication class for easy navigation.
    # 'cascade="all, delete-orphan"' means that if a posting is deleted,
    # all applications related to it are also deleted.
    applications = relationship("JobApplication", back_populates="job_posting", cascade="all, delete-orphan")

class JobApplication(Base):
    """
    Represents the 'job_applications' table in the database.
    """
    __tablename__ = 'job_applications'

    # --- Columns ---
    application_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_posting_id = Column(UUID(as_uuid=True), ForeignKey('job_postings.posting_id'), nullable=False)
    user_id = Column(String(255), nullable=False)
    cv_upload_key = Column(String(1024))
    cv_hash = Column(String(255), index=True)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    job_posting = relationship("JobPosting", back_populates="applications")
    analysis_result = relationship("CVAnalysisResult", back_populates="job_application", uselist=False,
                                   cascade="all, delete-orphan")

class CVAnalysisResult(Base):
    """
    Represents the 'cv_analysis_results' table in the database.
    """
    __tablename__ = 'cv_analysis_results'

    # --- Columns ---
    analysis_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_application_id = Column(UUID(as_uuid=True), ForeignKey('job_applications.application_id'),
                                nullable=False)
    analysis_data = Column(JSON)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships ---
    job_application = relationship("JobApplication", back_populates="analysis_result")