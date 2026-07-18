import type {
  AuditEntry,
  BlockDef,
  BundleInfo,
  ConnectionInfo,
  GitPushResult,
  TeamInfo,
  ConfigInfo,
  DeployResult,
  DraftDetail,
  FileContent,
  FileInfo,
  GraphModel,
  ValidateResult,
  VersionDetail,
  VersionInfo,
} from "./types";

// Same-origin requests: the Airflow session cookie (_token) is sent automatically.
const BASE = "/dagsmith/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

const encodePath = (path: string): string =>
  path.split("/").map(encodeURIComponent).join("/");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    let code = "error";
    let message = response.statusText;
    let detail: unknown;
    try {
      const body = (await response.json()) as {
        code?: string;
        message?: string;
        detail?: unknown;
      };
      if (body.code !== undefined && body.message !== undefined) {
        ({ code } = body);
        ({ message } = body);
        ({ detail } = body);
      } else if (body.detail !== undefined) {
        message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(response.status, code, message, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => request<ConfigInfo>("/config"),
  bundles: () => request<BundleInfo[]>("/bundles"),
  files: (bundle: string) =>
    request<FileInfo[]>(`/files?bundle=${encodeURIComponent(bundle)}`),
  readFile: (bundle: string, relPath: string) =>
    request<FileContent>(
      `/files/${encodePath(relPath)}?bundle=${encodeURIComponent(bundle)}`,
    ),
  openDraft: (bundle: string, relPath: string) =>
    request<DraftDetail>("/drafts", {
      method: "POST",
      body: JSON.stringify({ bundle, rel_path: relPath }),
    }),
  getDraft: (draftId: string) => request<DraftDetail>(`/drafts/${draftId}`),
  saveVersion: (
    draftId: string,
    body: {
      source: string;
      layout?: Record<string, unknown> | null;
      kind: "auto" | "manual";
      message?: string | null;
      expected_head_version_no: number;
    },
  ) =>
    request<VersionInfo>(`/drafts/${draftId}/versions`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  versions: (draftId: string) => request<VersionInfo[]>(`/drafts/${draftId}/versions`),
  version: (draftId: string, versionNo: number) =>
    request<VersionDetail>(`/drafts/${draftId}/versions/${versionNo}`),
  restore: (draftId: string, versionNo: number) =>
    request<VersionInfo>(`/drafts/${draftId}/restore/${versionNo}`, { method: "POST" }),
  reloadFromBundle: (draftId: string) =>
    request<DraftDetail>(`/drafts/${draftId}/reload`, { method: "POST" }),
  deploy: (draftId: string, expectedFileHash: string | null, versionNo?: number) =>
    request<DeployResult>(`/drafts/${draftId}/deploy`, {
      method: "POST",
      body: JSON.stringify({
        expected_file_hash: expectedFileHash,
        version_no: versionNo ?? null,
      }),
    }),
  validate: (source: string, deep = true) =>
    request<ValidateResult>("/validate", {
      method: "POST",
      body: JSON.stringify({ source, deep }),
    }),
  operators: () => request<BlockDef[]>("/operators"),
  connections: () => request<ConnectionInfo[]>("/connections"),
  codegen: (graph: GraphModel, baseSource?: string) =>
    request<{ source: string }>("/codegen", {
      method: "POST",
      body: JSON.stringify({ graph, base_source: baseSource ?? null }),
    }),
  parse: (source: string) =>
    request<{ graph: GraphModel | null; warnings: string[]; error: string | null }>(
      "/parse",
      { method: "POST", body: JSON.stringify({ source }) },
    ),
  audit: (limit = 100) => request<AuditEntry[]>(`/audit?limit=${limit}`),
  teams: () => request<TeamInfo[]>("/teams"),
  createTeam: (body: Omit<TeamInfo, "id" | "members">) =>
    request<TeamInfo>("/teams", { method: "POST", body: JSON.stringify(body) }),
  updateTeam: (teamId: string, body: Omit<TeamInfo, "id" | "members">) =>
    request<TeamInfo>(`/teams/${teamId}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteTeam: (teamId: string) =>
    request<undefined>(`/teams/${teamId}`, { method: "DELETE" }),
  addTeamMember: (teamId: string, username: string) =>
    request<undefined>(`/teams/${teamId}/members/${encodeURIComponent(username)}`, {
      method: "POST",
    }),
  removeTeamMember: (teamId: string, username: string) =>
    request<undefined>(`/teams/${teamId}/members/${encodeURIComponent(username)}`, {
      method: "DELETE",
    }),
  gitPush: (draftId: string) =>
    request<GitPushResult>(`/drafts/${draftId}/git-push`, { method: "POST" }),
  setFileTeam: (bundle: string, relPath: string, teamId: string | null) =>
    request<{ bundle: string; rel_path: string; team: string | null }>("/file-team", {
      method: "PUT",
      body: JSON.stringify({ bundle, rel_path: relPath, team_id: teamId }),
    }),
};
