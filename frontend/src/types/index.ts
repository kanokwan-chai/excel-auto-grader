export interface TeacherProfile {
  teacher_id: string;
  email: string;
  full_name: string;
  role: string;
  avatar_url?: string | null;
  school_name?: string | null;
  department?: string | null;
  phone?: string | null;
  bio?: string | null;
  preferences: {
    language: string;
    default_pass_percentage: number;
    default_numeric_tolerance: number;
    email_notifications: boolean;
    auto_recalculate_libreoffice: boolean;
    theme_accent: string;
  };
}

export interface DashboardSummary {
  kpis: {
    total_classes: number;
    total_students: number;
    total_assignments: number;
    grading_in_progress: number;
    completed_assignments: number;
    pending_files: number;
    average_score_percentage: number;
    connected_google_accounts: number;
  };
  assignment_score_chart: {
    assignment_id: string;
    name: string;
    average_score: number;
    max_score: number;
  }[];
  submission_progress_chart: {
    assignment_id: string;
    name: string;
    submitted: number;
    graded: number;
  }[];
  recent_assignments: {
    id: string;
    title: string;
    subject_name?: string | null;
    status: string;
    max_score: number;
    due_at?: string | null;
    created_at?: string | null;
  }[];
  recent_gradings: {
    result_id: string;
    assignment_title: string;
    student_name: string;
    final_score: number;
    max_score: number;
    percentage: number;
    status: string;
    is_confirmed: boolean;
    graded_at?: string | null;
  }[];
}

export interface TeacherClassItem {
  id: string;
  name: string;
  subject_code?: string | null;
  subject_name?: string | null;
  semester?: string | null;
  academic_year?: string | null;
  room?: string | null;
  description?: string | null;
  color_tag: string;
  student_count: number;
}

export interface StudentItem {
  id: string;
  student_code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  room?: string | null;
  seat_number?: number | null;
  email?: string | null;
  notes?: string | null;
  classes: { id: string; name: string }[];
}

export interface AssignmentItem {
  id: string;
  title: string;
  description?: string | null;
  subject_name?: string | null;
  class_id?: string | null;
  class_name?: string | null;
  due_at?: string | null;
  max_score: number;
  pass_score: number;
  max_files_allowed: number;
  allowed_extensions: string[];
  status: string;
  submission_count: number;
  graded_count: number;
  reference_file?: {
    id: string;
    filename: string;
    has_macros: boolean;
    sheet_metadata: Record<string, unknown>;
  } | null;
}

export interface RubricItem {
  id?: string;
  order_index: number;
  title: string;
  description?: string | null;
  category: string;
  sheet_name?: string | null;
  target_cell?: string | null;
  rule_config: Record<string, unknown>;
  max_points: number;
  min_points: number;
  allow_partial_credit: boolean;
  weight_importance: string;
  zero_on_error: boolean;
  is_enabled: boolean;
}

export interface Rubric {
  id: string;
  assignment_id?: string | null;
  name: string;
  description?: string | null;
  total_points: number;
  allocated_points: number;
  current_version: number;
  is_template: boolean;
  enabled_categories: string[];
  items: RubricItem[];
}

export interface GoogleAccountItem {
  id: string;
  google_user_id: string;
  google_email: string;
  display_name?: string | null;
  avatar_url?: string | null;
  status: "connected" | "expired" | "revoked" | "error";
  scopes: string[];
  token_expires_at?: string | null;
  has_refresh_token: boolean;
  last_synced_at?: string | null;
  last_error?: string | null;
  is_default: boolean;
}

export interface GoogleClassroomCourse {
  id: string;
  google_connection_id: string;
  google_account_email: string;
  google_account_status: string;
  google_course_id: string;
  name: string;
  section?: string | null;
  room?: string | null;
  course_state: string;
  student_count: number;
  last_synced_at?: string | null;
}

export interface ClassroomAssignmentItem {
  id: string;
  google_assignment_id: string;
  title: string;
  description?: string | null;
  state: string;
  max_points?: number | null;
  due_at?: string | null;
  turned_in_count: number;
  missing_count: number;
}

export interface ClassroomSubmissionItem {
  id: string;
  google_submission_id: string;
  student_name: string;
  student_email?: string | null;
  state: string;
  late: boolean;
  submitted_at?: string | null;
  attachments: {
    drive_file_id: string;
    title: string;
    mime_type?: string;
    modified_time?: string | null;
    size_bytes?: number | null;
    is_supported_excel: boolean;
  }[];
  selected_drive_file_id?: string | null;
  has_supported_excel: boolean;
  ui_status: "ready_for_grading" | "no_excel_file" | "not_submitted";
}

export interface GradingResultSummary {
  id: string;
  assignment_id: string;
  assignment_title: string;
  submission_id: string;
  student_name: string;
  student_code: string;
  auto_score: number;
  final_score: number;
  max_score: number;
  percentage: number;
  status: string;
  is_confirmed: boolean;
  graded_at?: string | null;
}

export interface GradingResultDetail extends GradingResultSummary {
  rubric_version: number;
  teacher_comment?: string | null;
  recalculated_with_libreoffice: boolean;
  details: {
    id: string;
    item_title: string;
    category: string;
    target_cell?: string | null;
    earned_points: number;
    deducted_points: number;
    max_points: number;
    passed: boolean;
    is_exempted: boolean;
    expected_value?: string | null;
    actual_value?: string | null;
    expected_formula?: string | null;
    actual_formula?: string | null;
    reason?: string | null;
    suggestion?: string | null;
  }[];
  errors: {
    id: string;
    error_code: string;
    severity: string;
    sheet_name?: string | null;
    cell_reference?: string | null;
    message_th: string;
    expected_detail?: string | null;
    actual_detail?: string | null;
    fix_suggestion_th?: string | null;
  }[];
  adjustments: {
    id: string;
    previous_score: number;
    new_score: number;
    reason: string;
    action_type: string;
    created_at?: string | null;
  }[];
}
