// Mirrors src/dagsmith/api/schemas.py (snake_case kept 1:1 with the wire format).

export type VersionKind = "auto" | "manual" | "deploy";
export type DraftStatus = "active" | "deployed" | "archived";
export type ErrorKind = "syntax" | "import" | "dag" | "timeout";

export type BundleInfo = {
  name: string;
  path: string;
  writable: boolean;
  git: boolean;
};

export type FileInfo = {
  rel_path: string;
  size: number;
  mtime: string;
  has_draft: boolean;
  deployed: boolean;
  dag_id: string | null;
  description: string | null;
  tags: string[];
  owner: string | null;
  created_by: string | null;
  team: string | null;
  editable: boolean;
};

export type FileContent = {
  bundle: string;
  rel_path: string;
  content: string;
  content_hash: string;
  mtime: string;
};

export type DraftSummary = {
  id: string;
  bundle: string;
  rel_path: string;
  status: DraftStatus;
  head_version_no: number;
  base_file_hash: string | null;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
};

export type DraftDetail = DraftSummary & {
  source: string;
  layout: Record<string, unknown> | null;
  live_file_hash: string | null;
  live_conflict: boolean;
};

export type VersionInfo = {
  version_no: number;
  kind: VersionKind;
  message: string | null;
  created_by: string | null;
  created_at: string;
  deployed_at: string | null;
};

export type VersionDetail = VersionInfo & {
  source: string;
  layout: Record<string, unknown> | null;
};

export type ValidationIssue = {
  line: number | null;
  col: number | null;
  message: string;
  kind: ErrorKind;
};

export type ValidateResult = {
  ok: boolean;
  errors: ValidationIssue[];
  dag_count: number | null;
};

export type DeployResult = {
  deployed_version_no: number;
  file_hash: string;
  backup_path: string | null;
  git_commit_sha: string | null;
  git_pushed: boolean;
  git_error: string | null;
};

export type AuditEntry = {
  ts: string;
  action: string;
  user: string | null;
  bundle: string | null;
  rel_path: string | null;
  version_no: number | null;
  hash_before: string | null;
  hash_after: string | null;
  git_commit_sha: string | null;
  git_pushed: boolean;
  git_error: string | null;
};

export type ConfigInfo = {
  deploy_enabled: boolean;
  autosave_interval: number;
  can_edit: boolean;
  can_deploy: boolean;
  is_admin: boolean;
  username: string | null;
};

export type TeamInfo = {
  id: string;
  name: string;
  description: string | null;
  bundle: string;
  path_prefix: string;
  git_remote_url: string | null;
  git_branch: string;
  git_push: boolean;
  members: string[];
};

export type ConnectionInfo = {
  conn_id: string;
  conn_type: string | null;
};

export type GitPushResult = {
  commit_sha: string | null;
  pushed: boolean;
  error: string | null;
  web_url: string | null;
};

export type DeployConflictDetail = {
  live_file_hash: string | null;
  live_content: string | null;
};

// --- Graph model (mirrors src/dagsmith/core/model.py) ---

export type Position = { x: number; y: number };

export type TaskNode = {
  id: string;
  block_id: string;
  params: Record<string, unknown>;
  position: Position | null;
  opaque: boolean;
  group_id: string | null;
};

export type GraphEdge = { source: string; target: string; label: string | null };

export const TRIGGER_RULES = [
  "all_success",
  "all_failed",
  "all_done",
  "all_done_min_one_success",
  "one_success",
  "one_failed",
  "one_done",
  "none_failed",
  "none_failed_min_one_success",
  "none_skipped",
  "all_skipped",
  "always",
] as const;

export type TaskGroupNode = {
  id: string;
  label: string | null;
  parent_id: string | null;
};

export type DagMeta = {
  dag_id: string;
  schedule: string | null;
  description: string | null;
  tags: string[];
  start_date: string | null;
  catchup: boolean | null;
  max_active_runs: number | null;
  owner: string | null;
  email: string | null;
  retries: number | null;
  retry_delay_s: number | null;
};

export type GraphModel = {
  dag: DagMeta;
  nodes: TaskNode[];
  edges: GraphEdge[];
  groups: TaskGroupNode[];
};

// --- Block catalog (mirrors src/dagsmith/core/catalog.py) ---

export type ParamType = "str" | "text" | "python" | "int" | "bool" | "dict";

export type BlockParam = {
  name: string;
  label: string;
  type: ParamType;
  required: boolean;
  default: string | number | boolean | null;
  help: string | null;
};

export type BlockDef = {
  block_id: string;
  label: string;
  category: string;
  description: string;
  import_stmt: string | null;
  params: BlockParam[];
};
