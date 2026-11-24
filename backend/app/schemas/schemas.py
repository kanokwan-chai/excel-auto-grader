"""Pydantic v2 Request & Response Schemas for Excel Auto Grader API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field


# --- Auth & Teacher Profile ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    school_name: str | None = None
    department: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class TeacherProfileUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    display_name: str | None = None
    school_name: str | None = None
    department: str | None = None
    phone: str | None = None
    bio: str | None = None
    avatar_url: str | None = None


class TeacherPreferenceUpdate(BaseModel):
    language: str | None = None
    default_pass_percentage: float | None = Field(default=None, ge=0, le=100)
    default_numeric_tolerance: float | None = Field(default=None, ge=0)
    email_notifications: bool | None = None
    auto_recalculate_libreoffice: bool | None = None
    theme_accent: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    teacher_id: str
    email: str
    full_name: str
    avatar_url: str | None = None


class TeacherMeResponse(BaseModel):
    teacher_id: str
    email: str
    full_name: str
    role: str
    avatar_url: str | None = None
    school_name: str | None = None
    department: str | None = None
    phone: str | None = None
    bio: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)


# --- Classes & Students ---
class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subject_code: str | None = None
    subject_name: str | None = None
    semester: str | None = None
    academic_year: str | None = None
    room: str | None = None
    description: str | None = None
    color_tag: str = "lavender"


class ClassUpdate(BaseModel):
    name: str | None = None
    subject_code: str | None = None
    subject_name: str | None = None
    semester: str | None = None
    academic_year: str | None = None
    room: str | None = None
    description: str | None = None
    color_tag: str | None = None
    is_archived: bool | None = None


class StudentCreate(BaseModel):
    student_code: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=150)
    last_name: str = Field(min_length=1, max_length=150)
    room: str | None = None
    seat_number: int | None = None
    email: str | None = None
    class_id: str | None = None
    notes: str | None = None


class StudentUpdate(BaseModel):
    student_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    room: str | None = None
    seat_number: int | None = None
    email: str | None = None
    notes: str | None = None


class StudentTransferRequest(BaseModel):
    from_class_id: str | None = None
    to_class_id: str


# --- Assignments ---
class AssignmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    subject_name: str | None = None
    class_id: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    max_score: float = Field(default=20.0, gt=0)
    pass_score: float = Field(default=10.0, ge=0)
    max_files_allowed: int = Field(default=1, ge=1)
    allowed_extensions: list[str] = Field(default_factory=lambda: [".xlsx", ".xls", ".xlsm"])
    status: str = "draft"


class AssignmentUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    subject_name: str | None = None
    class_id: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    max_score: float | None = Field(default=None, gt=0)
    pass_score: float | None = Field(default=None, ge=0)
    max_files_allowed: int | None = Field(default=None, ge=1)
    allowed_extensions: list[str] | None = None
    status: str | None = None


# --- Rubrics ---
class RubricItemPayload(BaseModel):
    order_index: int = 0
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    category: str
    sheet_name: str | None = None
    target_cell: str | None = None
    rule_config: dict[str, Any] = Field(default_factory=dict)
    max_points: float = Field(ge=0)
    min_points: float = Field(default=0.0, ge=0)
    allow_partial_credit: bool = True
    weight_importance: str = "normal"
    zero_on_error: bool = False
    is_enabled: bool = True


class RubricCreate(BaseModel):
    assignment_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    total_points: float = Field(default=20.0, gt=0)
    is_template: bool = False
    enabled_categories: list[str] = Field(
        default_factory=lambda: ["formula", "value", "position", "style", "structure", "chart", "completeness"]
    )
    items: list[RubricItemPayload] = Field(default_factory=list)
    change_note: str | None = "สร้างเกณฑ์เริ่มต้น"


class RubricUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    assignment_id: str | None = None
    total_points: float | None = Field(default=None, gt=0)
    is_template: bool | None = None
    enabled_categories: list[str] | None = None
    items: list[RubricItemPayload] | None = None
    change_note: str | None = "อัปเดตเกณฑ์การตรวจ"


# --- Grading & Adjustments ---
class StartGradingRequest(BaseModel):
    assignment_id: str
    rubric_id: str
    submission_ids: list[str] | None = None  # None = grade all eligible unconfirmed submissions
    force_regrade_unconfirmed: bool = True
    force_regrade_confirmed: bool = False


class GradeAdjustmentRequest(BaseModel):
    new_score: float = Field(ge=0)
    reason: str = Field(min_length=2)
    teacher_comment: str | None = None


class ExemptDetailRequest(BaseModel):
    detail_id: str
    exempt: bool = True
    reason: str = Field(min_length=2)


class SelectClassroomFileRequest(BaseModel):
    drive_file_id: str


class ClassroomGradeWizardRequest(BaseModel):
    google_connection_id: str
    google_classroom_id: str
    classroom_assignment_id: str
    rubric_id: str
    classroom_submission_ids: list[str] | None = None
