"""Complete SQLAlchemy 2.0 Multi-Teacher ORM Models (23 tables).

Compatible with both PostgreSQL (Supabase) and SQLite (for fast automated tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class UUIDStr(TypeDecorator):
    """Stores UUIDs compatibly across PostgreSQL (native UUID) and SQLite (VARCHAR), always returning Python str."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else str(value)

    def process_result_value(self, value, dialect):
        return None if value is None else str(value)


def _uuid_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    auth_uid: Mapped[str | None] = mapped_column(UUIDStr(), unique=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="teacher", nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["TeacherProfile | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences: Mapped["TeacherPreference | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class TeacherProfile(Base):
    __tablename__ = "teacher_profiles"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    teacher_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")


class TeacherPreference(Base):
    __tablename__ = "teacher_preferences"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="th")
    default_pass_percentage: Mapped[float] = mapped_column(Float, default=50.0)
    default_numeric_tolerance: Mapped[float] = mapped_column(Float, default=0.01)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_recalculate_libreoffice: Mapped[bool] = mapped_column(Boolean, default=True)
    theme_accent: Mapped[str] = mapped_column(String(50), default="lavender")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="preferences")


class GoogleConnection(Base):
    __tablename__ = "google_connections"
    __table_args__ = (UniqueConstraint("owner_user_id", "google_user_id", name="uq_google_conn_owner_account"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    google_email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(50), default="connected")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleClassroom(Base):
    __tablename__ = "google_classrooms"
    __table_args__ = (UniqueConstraint("google_connection_id", "google_course_id", name="uq_gc_conn_course"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_connection_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("google_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    google_course_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    course_state: Mapped[str] = mapped_column(String(50), default="ACTIVE")
    alternate_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    is_saved: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ClassroomCourseMembership(Base):
    __tablename__ = "classroom_course_memberships"
    __table_args__ = (UniqueConstraint("google_classroom_id", "google_user_id", name="uq_gc_member_course_user"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_classroom_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("google_classrooms.id", ondelete="CASCADE"), nullable=False)
    google_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="STUDENT")
    local_student_id: Mapped[str | None] = mapped_column(UUIDStr(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ClassroomAssignment(Base):
    __tablename__ = "classroom_assignments"
    __table_args__ = (UniqueConstraint("google_connection_id", "google_assignment_id", name="uq_gc_assign_conn_id"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_connection_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("google_connections.id", ondelete="CASCADE"), nullable=False)
    google_classroom_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("google_classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    google_assignment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(50), default="PUBLISHED")
    max_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alternate_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    turned_in_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    local_assignment_id: Mapped[str | None] = mapped_column(UUIDStr(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class TeacherClass(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    semester: Mapped[str | None] = mapped_column(String(50), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_classroom_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("google_classrooms.id", ondelete="SET NULL"), nullable=True)
    color_tag: Mapped[str] = mapped_column(String(50), default="lavender")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("owner_user_id", "student_code", name="uq_student_owner_code"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_code: Mapped[str] = mapped_column(String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(String(150), nullable=False)
    last_name: Mapped[str] = mapped_column(String(150), nullable=False)
    room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seat_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClassStudent(Base):
    __tablename__ = "class_students"
    __table_args__ = (UniqueConstraint("class_id", "student_id", name="uq_class_student"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    seat_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True, index=True)
    classroom_assignment_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("classroom_assignments.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=20.0)
    pass_score: Mapped[float] = mapped_column(Float, default=10.0)
    max_files_allowed: Mapped[int] = mapped_column(Integer, default=1)
    allowed_extensions: Mapped[list[str]] = mapped_column(JSON, default=lambda: [".xlsx", ".xls", ".xlsm"])
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReferenceFile(Base):
    __tablename__ = "reference_files"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    has_macros: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class GradingRubric(Base):
    __tablename__ = "grading_rubrics"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_points: Mapped[float] = mapped_column(Float, default=20.0)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_categories: Mapped[list[str]] = mapped_column(
        JSON,
        default=lambda: ["formula", "value", "position", "style", "structure", "chart", "completeness"],
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["RubricItem"]] = relationship(back_populates="rubric", cascade="all, delete-orphan", order_by="RubricItem.order_index")


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    __table_args__ = (UniqueConstraint("rubric_id", "version_number", name="uq_rubric_ver"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rubric_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("grading_rubrics.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RubricItem(Base):
    __tablename__ = "rubric_items"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rubric_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("grading_rubrics.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rule_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_points: Mapped[float] = mapped_column(Float, default=1.0)
    min_points: Mapped[float] = mapped_column(Float, default=0.0)
    allow_partial_credit: Mapped[bool] = mapped_column(Boolean, default=True)
    weight_importance: Mapped[str] = mapped_column(String(20), default="normal")
    zero_on_error: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    rubric: Mapped["GradingRubric"] = relationship(back_populates="items")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual_upload")
    student_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    student_code_matched: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submission_status: Mapped[str] = mapped_column(String(50), default="submitted")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    google_submission_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    files: Mapped[list["SubmissionFile"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class ClassroomSubmission(Base):
    __tablename__ = "classroom_submissions"
    __table_args__ = (UniqueConstraint("google_connection_id", "google_submission_id", name="uq_gc_sub_conn_id"),)

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_connection_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("google_connections.id", ondelete="CASCADE"), nullable=False)
    classroom_assignment_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("classroom_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    google_submission_id: Mapped[str] = mapped_column(String(255), nullable=False)
    google_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    student_name: Mapped[str] = mapped_column(String(255), nullable=False)
    student_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(50), default="CREATED")
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    selected_drive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_supported_excel: Mapped[bool] = mapped_column(Boolean, default=False)
    local_submission_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class SubmissionFile(Base):
    __tablename__ = "submission_files"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    google_drive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    has_macros: Mapped[bool] = mapped_column(Boolean, default=False)
    security_status: Mapped[str] = mapped_column(String(50), default="safe")
    security_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    submission: Mapped["Submission"] = relationship(back_populates="files")


class GradingJob(Base):
    __tablename__ = "grading_jobs"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    rubric_version_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("rubric_versions.id", ondelete="SET NULL"), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class GradingResult(Base):
    __tablename__ = "grading_results"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_job_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("grading_jobs.id", ondelete="SET NULL"), nullable=True)
    assignment_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_file_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("submission_files.id", ondelete="SET NULL"), nullable=True)
    student_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    rubric_version_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("rubric_versions.id", ondelete="SET NULL"), nullable=True)
    auto_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, default=20.0)
    percentage: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="graded")
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    teacher_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    recalculated_with_libreoffice: Mapped[bool] = mapped_column(Boolean, default=False)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    details: Mapped[list["GradingDetail"]] = relationship(back_populates="result", cascade="all, delete-orphan")
    errors: Mapped[list["GradingError"]] = relationship(back_populates="result", cascade="all, delete-orphan")
    adjustments: Mapped[list["GradeAdjustment"]] = relationship(back_populates="result", cascade="all, delete-orphan")


class GradingDetail(Base):
    __tablename__ = "grading_details"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_result_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("grading_results.id", ondelete="CASCADE"), nullable=False, index=True)
    rubric_item_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("rubric_items.id", ondelete="SET NULL"), nullable=True)
    item_title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    target_cell: Mapped[str | None] = mapped_column(String(100), nullable=True)
    earned_points: Mapped[float] = mapped_column(Float, default=0.0)
    deducted_points: Mapped[float] = mapped_column(Float, default=0.0)
    max_points: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_exempted: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    result: Mapped["GradingResult"] = relationship(back_populates="details")


class GradingError(Base):
    __tablename__ = "grading_errors"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_result_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("grading_results.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_detail_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("grading_details.id", ondelete="CASCADE"), nullable=True)
    error_code: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="error")
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cell_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message_th: Mapped[str] = mapped_column(Text, nullable=False)
    expected_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_suggestion_th: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    result: Mapped["GradingResult"] = relationship(back_populates="errors")


class GradeAdjustment(Base):
    __tablename__ = "grade_adjustments"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grading_result_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("grading_results.id", ondelete="CASCADE"), nullable=False, index=True)
    adjusted_by: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rubric_version_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("rubric_versions.id", ondelete="SET NULL"), nullable=True)
    previous_score: Mapped[float] = mapped_column(Float, nullable=False)
    new_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), default="score_override")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    result: Mapped["GradingResult"] = relationship(back_populates="adjustments")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(UUIDStr(), primary_key=True, default=_uuid_str)
    owner_user_id: Mapped[str] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(UUIDStr(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(UUIDStr(), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
