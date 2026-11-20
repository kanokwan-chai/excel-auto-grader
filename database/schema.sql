-- ============================================================================
-- Excel Auto Grader - Multi-Teacher SaaS Platform Database Schema
-- PostgreSQL 15+ / Supabase Compatible with Row Level Security (RLS)
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. USERS & TEACHER PROFILES (Multi-Teacher Isolation Root)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_uid UUID UNIQUE, -- Maps 1:1 to Supabase auth.users(id)
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'teacher' CHECK (role IN ('teacher', 'admin')),
    avatar_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.teacher_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    teacher_code VARCHAR(50) UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    school_name VARCHAR(255),
    department VARCHAR(255),
    phone VARCHAR(50),
    bio TEXT,
    avatar_storage_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.teacher_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    language VARCHAR(10) NOT NULL DEFAULT 'th',
    default_pass_percentage NUMERIC(5,2) NOT NULL DEFAULT 50.00,
    default_numeric_tolerance NUMERIC(10,6) NOT NULL DEFAULT 0.01,
    email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
    auto_recalculate_libreoffice BOOLEAN NOT NULL DEFAULT TRUE,
    theme_accent VARCHAR(50) NOT NULL DEFAULT 'lavender',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 2. GOOGLE ACCOUNTS & GOOGLE CLASSROOM (Multi-Account per Teacher)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.google_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    google_user_id VARCHAR(255) NOT NULL,
    google_email VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    avatar_url TEXT,
    -- Tokens MUST be encrypted with Fernet/AES-GCM before storage
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT,
    token_expires_at TIMESTAMPTZ,
    scopes JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'expired', 'revoked', 'error')),
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_google_connection_owner_account UNIQUE (owner_user_id, google_user_id)
);

CREATE INDEX IF NOT EXISTS idx_google_connections_owner ON public.google_connections(owner_user_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS public.google_classrooms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    google_connection_id UUID NOT NULL REFERENCES public.google_connections(id) ON DELETE CASCADE,
    google_course_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    section VARCHAR(255),
    description_heading VARCHAR(255),
    room VARCHAR(100),
    course_state VARCHAR(50) DEFAULT 'ACTIVE',
    alternate_link TEXT,
    student_count INTEGER DEFAULT 0,
    is_saved BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_google_classroom_conn_course UNIQUE (google_connection_id, google_course_id)
);

CREATE INDEX IF NOT EXISTS idx_google_classrooms_owner ON public.google_classrooms(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_google_classrooms_conn ON public.google_classrooms(google_connection_id);

-- Alias/view compatibility for classroom_courses
CREATE OR REPLACE VIEW public.classroom_courses AS
SELECT * FROM public.google_classrooms;

CREATE TABLE IF NOT EXISTS public.classroom_course_memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    google_classroom_id UUID NOT NULL REFERENCES public.google_classrooms(id) ON DELETE CASCADE,
    google_user_id VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    full_name VARCHAR(255) NOT NULL,
    photo_url TEXT,
    role VARCHAR(50) NOT NULL DEFAULT 'STUDENT' CHECK (role IN ('STUDENT', 'TEACHER')),
    local_student_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_classroom_membership_course_user UNIQUE (google_classroom_id, google_user_id)
);

CREATE INDEX IF NOT EXISTS idx_classroom_memberships_owner ON public.classroom_course_memberships(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_classroom_memberships_course ON public.classroom_course_memberships(google_classroom_id);

CREATE TABLE IF NOT EXISTS public.classroom_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    google_connection_id UUID NOT NULL REFERENCES public.google_connections(id) ON DELETE CASCADE,
    google_classroom_id UUID NOT NULL REFERENCES public.google_classrooms(id) ON DELETE CASCADE,
    google_assignment_id VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    state VARCHAR(50) DEFAULT 'PUBLISHED',
    max_points NUMERIC(8,2),
    due_at TIMESTAMPTZ,
    alternate_link TEXT,
    turned_in_count INTEGER DEFAULT 0,
    missing_count INTEGER DEFAULT 0,
    local_assignment_id UUID,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_classroom_assignment_conn_id UNIQUE (google_connection_id, google_assignment_id)
);

CREATE INDEX IF NOT EXISTS idx_classroom_assignments_owner ON public.classroom_assignments(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_classroom_assignments_course ON public.classroom_assignments(google_classroom_id);

-- ============================================================================
-- 3. CLASSES & STUDENTS (Teacher-Owned Local Classes)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.classes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    subject_code VARCHAR(100),
    subject_name VARCHAR(255),
    semester VARCHAR(50),
    academic_year VARCHAR(20),
    room VARCHAR(100),
    description TEXT,
    google_classroom_id UUID REFERENCES public.google_classrooms(id) ON DELETE SET NULL,
    color_tag VARCHAR(50) DEFAULT 'lavender',
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_classes_owner ON public.classes(owner_user_id) WHERE deleted_at IS NULL;

-- Multi-tenant teacher_classes mapping for future co-teaching / explicit ownership
CREATE TABLE IF NOT EXISTS public.teacher_classes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    class_id UUID NOT NULL REFERENCES public.classes(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'owner' CHECK (role IN ('owner', 'co_teacher')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_teacher_class UNIQUE (owner_user_id, class_id)
);

CREATE TABLE IF NOT EXISTS public.students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    student_code VARCHAR(100) NOT NULL,
    first_name VARCHAR(150) NOT NULL,
    last_name VARCHAR(150) NOT NULL,
    room VARCHAR(100),
    seat_number INTEGER,
    email VARCHAR(255),
    google_user_id VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_student_owner_code UNIQUE (owner_user_id, student_code)
);

CREATE INDEX IF NOT EXISTS idx_students_owner ON public.students(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_students_search ON public.students(owner_user_id, student_code, first_name, last_name);

CREATE TABLE IF NOT EXISTS public.class_students (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    class_id UUID NOT NULL REFERENCES public.classes(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
    seat_number INTEGER,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_class_student UNIQUE (class_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_class_students_owner ON public.class_students(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_class_students_class ON public.class_students(class_id);

-- ============================================================================
-- 4. ASSIGNMENTS, REFERENCE FILES & RUBRICS (Versioned)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    class_id UUID REFERENCES public.classes(id) ON DELETE SET NULL,
    classroom_assignment_id UUID REFERENCES public.classroom_assignments(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    subject_name VARCHAR(255),
    start_at TIMESTAMPTZ,
    due_at TIMESTAMPTZ,
    max_score NUMERIC(8,2) NOT NULL DEFAULT 20.00 CHECK (max_score > 0),
    pass_score NUMERIC(8,2) NOT NULL DEFAULT 10.00,
    max_files_allowed INTEGER NOT NULL DEFAULT 1 CHECK (max_files_allowed >= 1),
    allowed_extensions JSONB NOT NULL DEFAULT '[".xlsx", ".xls", ".xlsm"]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'grading', 'completed', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_assignments_owner ON public.assignments(owner_user_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_assignments_class ON public.assignments(class_id);

CREATE TABLE IF NOT EXISTS public.reference_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    original_filename VARCHAR(500) NOT NULL,
    storage_path TEXT NOT NULL, -- /users/{user_id}/references/{file}
    file_size_bytes BIGINT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    sheet_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    has_macros BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reference_files_owner ON public.reference_files(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_reference_files_assignment ON public.reference_files(assignment_id);

CREATE TABLE IF NOT EXISTS public.grading_rubrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES public.assignments(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    total_points NUMERIC(8,2) NOT NULL DEFAULT 20.00,
    current_version INTEGER NOT NULL DEFAULT 1,
    is_template BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_categories JSONB NOT NULL DEFAULT '["formula", "value", "position", "style", "structure", "chart", "completeness"]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_grading_rubrics_owner ON public.grading_rubrics(owner_user_id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS public.rubric_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    rubric_id UUID NOT NULL REFERENCES public.grading_rubrics(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    total_points NUMERIC(8,2) NOT NULL,
    snapshot_json JSONB NOT NULL, -- Immutable snapshot of all rubric items used at grading time
    change_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rubric_version UNIQUE (rubric_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_rubric_versions_owner ON public.rubric_versions(owner_user_id);

CREATE TABLE IF NOT EXISTS public.rubric_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    rubric_id UUID NOT NULL REFERENCES public.grading_rubrics(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL DEFAULT 0,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL CHECK (category IN ('formula', 'value', 'position', 'style', 'structure', 'chart', 'completeness')),
    sheet_name VARCHAR(255),
    target_cell VARCHAR(100), -- e.g. 'D2' or 'D2:D20'
    rule_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    max_points NUMERIC(8,2) NOT NULL CHECK (max_points >= 0),
    min_points NUMERIC(8,2) NOT NULL DEFAULT 0 CHECK (min_points >= 0),
    allow_partial_credit BOOLEAN NOT NULL DEFAULT TRUE,
    weight_importance VARCHAR(20) NOT NULL DEFAULT 'normal' CHECK (weight_importance IN ('low', 'normal', 'high', 'critical')),
    zero_on_error BOOLEAN NOT NULL DEFAULT FALSE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rubric_items_rubric ON public.rubric_items(rubric_id);

-- ============================================================================
-- 5. SUBMISSIONS & CLASSROOM SUBMISSIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    student_id UUID REFERENCES public.students(id) ON DELETE SET NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'manual_upload' CHECK (source IN ('manual_upload', 'google_classroom')),
    student_display_name VARCHAR(255),
    student_code_matched VARCHAR(100),
    submission_status VARCHAR(50) NOT NULL DEFAULT 'submitted' CHECK (
        submission_status IN ('missing', 'created', 'submitted', 'turned_in', 'returned', 'reclaimed_by_student', 'no_excel_file', 'error')
    ),
    submitted_at TIMESTAMPTZ,
    google_submission_id VARCHAR(255),
    is_late BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submissions_owner ON public.submissions(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_assignment ON public.submissions(assignment_id);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON public.submissions(student_id);

CREATE TABLE IF NOT EXISTS public.classroom_submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    google_connection_id UUID NOT NULL REFERENCES public.google_connections(id) ON DELETE CASCADE,
    classroom_assignment_id UUID NOT NULL REFERENCES public.classroom_assignments(id) ON DELETE CASCADE,
    google_submission_id VARCHAR(255) NOT NULL,
    google_user_id VARCHAR(255) NOT NULL,
    student_name VARCHAR(255) NOT NULL,
    student_email VARCHAR(255),
    state VARCHAR(50) NOT NULL CHECK (state IN ('NEW', 'CREATED', 'TURNED_IN', 'RETURNED', 'RECLAIMED_BY_STUDENT', 'SUBMISSION_STATE_UNSPECIFIED')),
    late BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at TIMESTAMPTZ,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array of Drive file metadata
    selected_drive_file_id VARCHAR(255),
    has_supported_excel BOOLEAN NOT NULL DEFAULT FALSE,
    local_submission_id UUID REFERENCES public.submissions(id) ON DELETE SET NULL,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_classroom_submission_conn_id UNIQUE (google_connection_id, google_submission_id)
);

CREATE INDEX IF NOT EXISTS idx_classroom_submissions_owner ON public.classroom_submissions(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_classroom_submissions_assignment ON public.classroom_submissions(classroom_assignment_id);

CREATE TABLE IF NOT EXISTS public.submission_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    submission_id UUID NOT NULL REFERENCES public.submissions(id) ON DELETE CASCADE,
    original_filename VARCHAR(500) NOT NULL,
    storage_path TEXT NOT NULL, -- /users/{user_id}/submissions/{file}
    file_extension VARCHAR(20) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    sha256_hash VARCHAR(64) NOT NULL,
    google_drive_file_id VARCHAR(255),
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    has_macros BOOLEAN NOT NULL DEFAULT FALSE,
    security_status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (security_status IN ('pending', 'safe', 'quarantined', 'corrupted')),
    security_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_submission_files_owner ON public.submission_files(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_submission_files_submission ON public.submission_files(submission_id);

-- ============================================================================
-- 6. GRADING JOBS, RESULTS, DETAILS, ERRORS & ADJUSTMENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.grading_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    assignment_id UUID NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    rubric_version_id UUID REFERENCES public.rubric_versions(id) ON DELETE SET NULL,
    celery_task_id VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'partial_failed', 'failed')),
    total_files INTEGER NOT NULL DEFAULT 0,
    processed_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    error_log TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grading_jobs_owner ON public.grading_jobs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_grading_jobs_assignment ON public.grading_jobs(assignment_id);

CREATE TABLE IF NOT EXISTS public.grading_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    grading_job_id UUID REFERENCES public.grading_jobs(id) ON DELETE SET NULL,
    assignment_id UUID NOT NULL REFERENCES public.assignments(id) ON DELETE CASCADE,
    submission_id UUID NOT NULL REFERENCES public.submissions(id) ON DELETE CASCADE,
    submission_file_id UUID REFERENCES public.submission_files(id) ON DELETE SET NULL,
    student_id UUID REFERENCES public.students(id) ON DELETE SET NULL,
    rubric_version_id UUID REFERENCES public.rubric_versions(id) ON DELETE SET NULL,
    auto_score NUMERIC(8,2) NOT NULL DEFAULT 0,
    final_score NUMERIC(8,2) NOT NULL DEFAULT 0,
    max_score NUMERIC(8,2) NOT NULL DEFAULT 20,
    percentage NUMERIC(6,2) NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'graded' CHECK (status IN ('pending', 'graded', 'needs_review', 'confirmed', 'error')),
    is_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_at TIMESTAMPTZ,
    confirmed_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
    teacher_comment TEXT,
    recalculated_with_libreoffice BOOLEAN NOT NULL DEFAULT FALSE,
    graded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grading_results_owner ON public.grading_results(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_grading_results_assignment ON public.grading_results(assignment_id);
CREATE INDEX IF NOT EXISTS idx_grading_results_submission ON public.grading_results(submission_id);

CREATE TABLE IF NOT EXISTS public.grading_details (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    grading_result_id UUID NOT NULL REFERENCES public.grading_results(id) ON DELETE CASCADE,
    rubric_item_id UUID REFERENCES public.rubric_items(id) ON DELETE SET NULL,
    item_title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    target_cell VARCHAR(100),
    earned_points NUMERIC(8,2) NOT NULL DEFAULT 0,
    deducted_points NUMERIC(8,2) NOT NULL DEFAULT 0,
    max_points NUMERIC(8,2) NOT NULL DEFAULT 0,
    passed BOOLEAN NOT NULL DEFAULT FALSE,
    is_exempted BOOLEAN NOT NULL DEFAULT FALSE,
    expected_value TEXT,
    actual_value TEXT,
    expected_formula TEXT,
    actual_formula TEXT,
    reason TEXT,
    suggestion TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grading_details_result ON public.grading_details(grading_result_id);

CREATE TABLE IF NOT EXISTS public.grading_errors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    grading_result_id UUID NOT NULL REFERENCES public.grading_results(id) ON DELETE CASCADE,
    grading_detail_id UUID REFERENCES public.grading_details(id) ON DELETE CASCADE,
    error_code VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'error' CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    sheet_name VARCHAR(255),
    cell_reference VARCHAR(100),
    message_th TEXT NOT NULL,
    expected_detail TEXT,
    actual_detail TEXT,
    fix_suggestion_th TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grading_errors_result ON public.grading_errors(grading_result_id);

CREATE TABLE IF NOT EXISTS public.grade_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    grading_result_id UUID NOT NULL REFERENCES public.grading_results(id) ON DELETE CASCADE,
    adjusted_by UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    rubric_version_id UUID REFERENCES public.rubric_versions(id) ON DELETE SET NULL,
    previous_score NUMERIC(8,2) NOT NULL,
    new_score NUMERIC(8,2) NOT NULL,
    reason TEXT NOT NULL,
    action_type VARCHAR(50) NOT NULL DEFAULT 'score_override' CHECK (
        action_type IN ('score_override', 'exempt_item', 'confirm', 'unconfirm', 'regrade', 'comment')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grade_adjustments_owner ON public.grade_adjustments(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_grade_adjustments_result ON public.grade_adjustments(grading_result_id);

-- ============================================================================
-- 7. ACTIVITY LOGS (Audit Trail)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.activity_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_owner ON public.activity_logs(owner_user_id, created_at DESC);

-- ============================================================================
-- 8. UPDATED_AT TRIGGERS
-- ============================================================================

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'users', 'teacher_profiles', 'teacher_preferences',
        'google_connections', 'google_classrooms', 'classroom_course_memberships',
        'classroom_assignments', 'classroom_submissions',
        'classes', 'students', 'assignments', 'reference_files',
        'grading_rubrics', 'rubric_items', 'submissions',
        'grading_jobs', 'grading_results'
    ]
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS trg_%I_updated_at ON public.%I;
             CREATE TRIGGER trg_%I_updated_at
             BEFORE UPDATE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();',
            tbl, tbl, tbl, tbl
        );
    END LOOP;
END $$;

-- ============================================================================
-- 9. ROW LEVEL SECURITY (RLS) POLICIES - STRICT MULTI-TEACHER ISOLATION
-- ============================================================================

-- Provide a safe fallback auth.uid() when running on standalone PostgreSQL (Docker)
CREATE SCHEMA IF NOT EXISTS auth;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'auth' AND p.proname = 'uid'
    ) THEN
        EXECUTE 'CREATE FUNCTION auth.uid() RETURNS UUID AS $fn$ SELECT NULL::UUID; $fn$ LANGUAGE sql STABLE;';
    END IF;
END $$;

-- Helper to resolve current authenticated user's internal users.id from Supabase auth.uid()
CREATE OR REPLACE FUNCTION public.current_teacher_id()
RETURNS UUID AS $$
    SELECT id FROM public.users WHERE auth_uid = auth.uid() AND deleted_at IS NULL LIMIT 1;
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Enable RLS on users & teacher_profiles
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teacher_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_self_isolation ON public.users;
CREATE POLICY users_self_isolation ON public.users
    USING (auth_uid = auth.uid())
    WITH CHECK (auth_uid = auth.uid());

DROP POLICY IF EXISTS teacher_profiles_self_isolation ON public.teacher_profiles;
CREATE POLICY teacher_profiles_self_isolation ON public.teacher_profiles
    USING (user_id = public.current_teacher_id())
    WITH CHECK (user_id = public.current_teacher_id());

-- Enable strict owner_user_id RLS on every tenant-owned table
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'teacher_preferences',
        'google_connections',
        'google_classrooms',
        'classroom_course_memberships',
        'classroom_assignments',
        'classroom_submissions',
        'classes',
        'teacher_classes',
        'students',
        'class_students',
        'assignments',
        'reference_files',
        'grading_rubrics',
        'rubric_versions',
        'rubric_items',
        'submissions',
        'submission_files',
        'grading_jobs',
        'grading_results',
        'grading_details',
        'grading_errors',
        'grade_adjustments',
        'activity_logs'
    ]
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('DROP POLICY IF EXISTS %I_owner_isolation ON public.%I;', tbl, tbl);
        EXECUTE format(
            'CREATE POLICY %I_owner_isolation ON public.%I
             FOR ALL
             USING (owner_user_id = public.current_teacher_id())
             WITH CHECK (owner_user_id = public.current_teacher_id());',
            tbl, tbl
        );
    END LOOP;
END $$;

-- ============================================================================
-- 10. SUPABASE STORAGE BUCKET & RLS POLICIES (Per-Teacher Folder Isolation)
-- Storage Paths:
--   /users/{user_id}/references/
--   /users/{user_id}/submissions/
--   /users/{user_id}/reports/
--   /users/{user_id}/exports/
-- ============================================================================

-- Run in Supabase SQL Editor where storage.buckets exists:
-- INSERT INTO storage.buckets (id, name, public, file_size_limit)
-- VALUES ('excel-auto-grader', 'excel-auto-grader', false, 20971520)
-- ON CONFLICT (id) DO NOTHING;
--
-- CREATE POLICY "Teacher owns storage folder"
-- ON storage.objects FOR ALL
-- USING (
--   bucket_id = 'excel-auto-grader'
--   AND (storage.foldername(name))[1] = 'users'
--   AND (storage.foldername(name))[2] = public.current_teacher_id()::text
-- )
-- WITH CHECK (
--   bucket_id = 'excel-auto-grader'
--   AND (storage.foldername(name))[1] = 'users'
--   AND (storage.foldername(name))[2] = public.current_teacher_id()::text
-- );
