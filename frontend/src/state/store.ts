import { create } from "zustand";

import { api, ApiError } from "src/api/client";
import type {
  BlockDef,
  BundleInfo,
  ConfigInfo,
  ConnectionInfo,
  DeployConflictDetail,
  DraftDetail,
  FileInfo,
  GraphModel,
  TeamInfo,
  ValidateResult,
  VersionInfo,
} from "src/api/types";

export type Notice = { type: "info" | "success" | "error"; text: string };
export type EditorMode = "code" | "visual" | "split";

/** Carry canvas positions over from the previous graph (matched by node id). */
const mergePositions = (parsed: GraphModel, previous?: GraphModel): GraphModel => {
  if (!previous) {
    return parsed;
  }
  const positions = new Map(
    previous.nodes
      .filter((node) => node.position !== null)
      .map((node) => [node.id, node.position]),
  );
  return {
    ...parsed,
    nodes: parsed.nodes.map((node) => ({
      ...node,
      position: node.position ?? positions.get(node.id) ?? null,
    })),
  };
};

type EditorState = {
  loading: boolean;
  config?: ConfigInfo;
  bundles: BundleInfo[];
  teams: TeamInfo[];
  connections: ConnectionInfo[];
  selectedBundle?: string;
  files: FileInfo[];

  draft?: DraftDetail;
  source: string;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
  liveFileHash: string | null;

  blocks: BlockDef[];
  graph?: GraphModel;
  mode: EditorMode;
  selectedNodeId?: string;
  parseError?: string;
  parseWarnings: string[];
  regenerating: boolean;

  validation?: ValidateResult;
  validating: boolean;
  history?: VersionInfo[];
  showHistory: boolean;
  deployConflict?: DeployConflictDetail;
  saveConflictHead?: number;
  deploying: boolean;
  notice?: Notice;

  init: () => Promise<void>;
  selectBundle: (name: string) => Promise<void>;
  refreshFiles: () => Promise<void>;
  openFile: (relPath: string, forceReadOnly?: boolean) => Promise<void>;
  closeFile: () => void;
  setSource: (text: string) => void;
  setMode: (mode: EditorMode) => void;
  selectNode: (nodeId?: string) => void;
  multiSelection: string[];
  setMultiSelection: (nodeIds: string[]) => void;
  mutateGraph: (updater: (graph: GraphModel) => GraphModel, layoutOnly?: boolean) => void;
  addBlock: (blockId: string, position?: { x: number; y: number }) => void;
  assignToGroup: (nodeIds: string[], groupId: string | null) => void;
  createGroupWith: (nodeIds: string[]) => void;
  renameGroup: (groupId: string, newLocalId: string) => void;
  deleteGroup: (groupId: string) => void;
  moveGroup: (groupId: string, dx: number, dy: number) => void;
  save: (kind: "auto" | "manual", message?: string) => Promise<void>;
  reloadDraft: () => Promise<void>;
  loadFromBundle: () => Promise<void>;
  validate: () => Promise<void>;
  deploy: (expectedHash?: string | null) => Promise<void>;
  cancelDeployConflict: () => void;
  toggleHistory: () => Promise<void>;
  restore: (versionNo: number) => Promise<void>;
  setNotice: (notice?: Notice) => void;
};

const errorNotice = (err: unknown): Notice => ({
  type: "error",
  text: err instanceof Error ? err.message : String(err),
});

export const useStore = create<EditorState>((set, get) => ({
  loading: true,
  bundles: [],
  teams: [],
  connections: [],
  files: [],
  source: "",
  dirty: false,
  saving: false,
  readOnly: true,
  liveFileHash: null,
  validating: false,
  showHistory: false,
  deploying: false,
  blocks: [],
  mode: "code",
  parseWarnings: [],
  regenerating: false,

  init: async () => {
    try {
      const [config, bundles, blocks, teams, connections] = await Promise.all([
        api.config(),
        api.bundles(),
        api.operators().catch(() => [] as BlockDef[]),
        api.teams().catch(() => [] as TeamInfo[]),
        api.connections().catch(() => [] as ConnectionInfo[]),
      ]);
      set({
        config,
        bundles,
        blocks,
        teams,
        connections,
        loading: false,
        readOnly: !config.can_edit,
      });
      const first = bundles[0];
      if (first) {
        await get().selectBundle(first.name);
      }
    } catch (err) {
      set({ loading: false, notice: errorNotice(err) });
    }
  },

  selectBundle: async (name) => {
    set({ selectedBundle: name, files: [] });
    await get().refreshFiles();
  },

  refreshFiles: async () => {
    const bundle = get().selectedBundle;
    if (!bundle) {
      return;
    }
    try {
      set({ files: await api.files(bundle) });
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  openFile: async (relPath, forceReadOnly = false) => {
    const { selectedBundle, config } = get();
    if (!selectedBundle) {
      return;
    }
    try {
      if (config?.can_edit && !forceReadOnly) {
        const draft = await api.openDraft(selectedBundle, relPath);
        const layoutGraph = (draft.layout as { graph?: GraphModel } | null)?.graph;
        const parsed = await api.parse(draft.source);
        const graph = parsed.graph ? mergePositions(parsed.graph, layoutGraph) : undefined;
        set({
          draft,
          source: draft.source,
          dirty: false,
          readOnly: false,
          liveFileHash: draft.live_file_hash,
          graph,
          mode: graph ? "visual" : "code",
          parseError: parsed.error ?? undefined,
          parseWarnings: parsed.warnings,
          selectedNodeId: undefined,
          validation: undefined,
          history: undefined,
          showHistory: false,
          deployConflict: undefined,
          saveConflictHead: undefined,
        });
      } else {
        const file = await api.readFile(selectedBundle, relPath);
        set({
          draft: undefined,
          source: file.content,
          dirty: false,
          readOnly: true,
          liveFileHash: file.content_hash,
          validation: undefined,
        });
      }
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  closeFile: () => {
    set({
      draft: undefined,
      source: "",
      dirty: false,
      graph: undefined,
      mode: "code",
      selectedNodeId: undefined,
      parseError: undefined,
      parseWarnings: [],
      validation: undefined,
      history: undefined,
      showHistory: false,
      deployConflict: undefined,
      saveConflictHead: undefined,
    });
    void get().refreshFiles();
  },

  setSource: (text) => {
    set({
      source: text,
      dirty: text !== get().draft?.source ? true : get().dirty,
    });
    scheduleParse();
  },

  setMode: (mode) => set({ mode }),

  selectNode: (nodeId) => set({ selectedNodeId: nodeId }),

  multiSelection: [],
  setMultiSelection: (nodeIds) => set({ multiSelection: nodeIds }),

  assignToGroup: (nodeIds, groupId) => {
    const eligible = new Set(
      (get().graph?.nodes ?? [])
        .filter((n) => nodeIds.includes(n.id) && !n.opaque)
        .map((n) => n.id),
    );
    if (eligible.size === 0) {
      set({
        notice: {
          type: "info",
          text: "Code-only blocks can be grouped only in the Code view",
        },
      });
      return;
    }
    get().mutateGraph((graph) => ({
      ...graph,
      nodes: graph.nodes.map((n) =>
        eligible.has(n.id) ? { ...n, group_id: groupId } : n,
      ),
    }));
  },

  createGroupWith: (nodeIds) => {
    const graph = get().graph;
    if (!graph) {
      return;
    }
    const existing = new Set(graph.groups.map((g) => g.id));
    let index = 1;
    while (existing.has(`group_${index}`)) {
      index += 1;
    }
    const groupId = `group_${index}`;
    const eligible = new Set(
      graph.nodes.filter((n) => nodeIds.includes(n.id) && !n.opaque).map((n) => n.id),
    );
    if (eligible.size === 0) {
      set({
        notice: {
          type: "info",
          text: "Select at least one task (code-only blocks cannot be grouped visually)",
        },
      });
      return;
    }
    get().mutateGraph((g) => ({
      ...g,
      groups: [...g.groups, { id: groupId, label: groupId, parent_id: null }],
      nodes: g.nodes.map((n) => (eligible.has(n.id) ? { ...n, group_id: groupId } : n)),
    }));
    set({ multiSelection: [] });
  },

  renameGroup: (groupId, newLocalId) => {
    const graph = get().graph;
    if (!graph) {
      return;
    }
    const group = graph.groups.find((g) => g.id === groupId);
    if (!group || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(newLocalId)) {
      return;
    }
    if (graph.groups.some((g) => g.parent_id === groupId)) {
      set({
        notice: {
          type: "info",
          text: "Groups with nested groups can be renamed only in the Code view",
        },
      });
      return;
    }
    const newId = group.parent_id ? `${group.parent_id}.${newLocalId}` : newLocalId;
    if (newId === groupId || graph.groups.some((g) => g.id === newId)) {
      return;
    }
    get().mutateGraph((g) => ({
      ...g,
      groups: g.groups.map((existing) =>
        existing.id === groupId
          ? { id: newId, label: newLocalId, parent_id: existing.parent_id }
          : existing,
      ),
      nodes: g.nodes.map((n) => (n.group_id === groupId ? { ...n, group_id: newId } : n)),
    }));
  },

  deleteGroup: (groupId) => {
    const graph = get().graph;
    if (!graph) {
      return;
    }
    const group = graph.groups.find((g) => g.id === groupId);
    if (!group) {
      return;
    }
    const inSubtree = (id: string | null) =>
      id !== null && (id === groupId || id.startsWith(`${groupId}.`));
    // Cascade: nested groups go too; member tasks land in the parent group.
    get().mutateGraph((g) => ({
      ...g,
      groups: g.groups.filter((existing) => !inSubtree(existing.id)),
      nodes: g.nodes.map((n) =>
        inSubtree(n.group_id) ? { ...n, group_id: group.parent_id } : n,
      ),
    }));
  },

  moveGroup: (groupId, dx, dy) => {
    get().mutateGraph(
      (g) => ({
        ...g,
        nodes: g.nodes.map((n) => {
          const member =
            n.group_id !== null &&
            (n.group_id === groupId || n.group_id.startsWith(`${groupId}.`));
          if (!member || !n.position) {
            return n;
          }
          return { ...n, position: { x: n.position.x + dx, y: n.position.y + dy } };
        }),
      }),
      true, // positions only
    );
  },

  mutateGraph: (updater, layoutOnly = false) => {
    const current = get().graph;
    if (!current) {
      return;
    }
    const next = updater(structuredClone(current));
    set({ graph: next, dirty: true });
    if (!layoutOnly) {
      scheduleRegen();
    }
  },

  addBlock: (blockId, position) => {
    const block = get().blocks.find((b) => b.block_id === blockId);
    if (!block) {
      return;
    }
    const params: Record<string, unknown> = {};
    for (const param of block.params) {
      if (param.default !== null) {
        params[param.name] = param.default;
      }
    }
    get().mutateGraph((graph) => {
      const existing = new Set(graph.nodes.map((n) => n.id));
      const base =
        block.label
          .replace(/(Operator|Sensor)$/, "")
          .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
          .toLowerCase()
          .replace(/\W/g, "_")
          .replace(/^_+|_+$/g, "") || "task";
      let index = 1;
      while (existing.has(`${base}_${index}`)) {
        index += 1;
      }
      const taskId = `${base}_${index}`;
      get().selectNode(taskId);
      return {
        ...graph,
        nodes: [
          ...graph.nodes,
          {
            id: taskId,
            block_id: block.block_id,
            params,
            // Fallback grid position matches the horizontal canvas flow.
            position: position ?? {
              x: 80 + (graph.nodes.length % 3) * 280,
              y: 60 + Math.floor(graph.nodes.length / 3) * 130,
            },
            opaque: false,
            group_id: null,
          },
        ],
      };
    });
  },

  save: async (kind, message) => {
    const { draft, source, dirty, saving } = get();
    if (!draft || saving || (kind === "auto" && !dirty)) {
      return;
    }
    set({ saving: true });
    try {
      const graph = get().graph;
      const version = await api.saveVersion(draft.id, {
        source,
        layout: graph ? { graph } : null,
        kind,
        message: message ?? null,
        expected_head_version_no: draft.head_version_no,
      });
      set({
        draft: { ...draft, source, head_version_no: version.version_no, status: "active" },
        dirty: false,
        saving: false,
        saveConflictHead: undefined,
        ...(kind === "manual"
          ? { notice: { type: "success", text: `Saved as v${version.version_no}` } }
          : {}),
      });
      if (get().showHistory) {
        set({ history: await api.versions(draft.id) });
      }
    } catch (err) {
      set({ saving: false });
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as { head_version_no?: number } | undefined;
        set({ saveConflictHead: detail?.head_version_no });
      } else {
        set({ notice: errorNotice(err) });
      }
    }
  },

  reloadDraft: async () => {
    const { draft } = get();
    if (!draft) {
      return;
    }
    try {
      const fresh = await api.getDraft(draft.id);
      const layoutGraph = (fresh.layout as { graph?: GraphModel } | null)?.graph;
      const parsed = await api.parse(fresh.source);
      const graph = parsed.graph ? mergePositions(parsed.graph, layoutGraph) : undefined;
      set({
        draft: fresh,
        source: fresh.source,
        dirty: false,
        liveFileHash: fresh.live_file_hash,
        saveConflictHead: undefined,
        graph,
        mode: graph ? get().mode : "code",
        parseError: parsed.error ?? undefined,
        parseWarnings: parsed.warnings,
        selectedNodeId: undefined,
      });
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  loadFromBundle: async () => {
    const { draft } = get();
    if (!draft) {
      return;
    }
    try {
      const fresh = await api.reloadFromBundle(draft.id);
      const parsed = await api.parse(fresh.source);
      const graph = parsed.graph ? mergePositions(parsed.graph, undefined) : undefined;
      set({
        draft: fresh,
        source: fresh.source,
        dirty: false,
        liveFileHash: fresh.live_file_hash,
        saveConflictHead: undefined,
        graph,
        mode: graph ? get().mode : "code",
        parseError: parsed.error ?? undefined,
        parseWarnings: parsed.warnings,
        validation: undefined,
        selectedNodeId: undefined,
        notice: { type: "success", text: "Loaded the deployed file from the bundle" },
      });
      if (get().showHistory) {
        set({ history: await api.versions(draft.id) });
      }
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  validate: async () => {
    set({ validating: true });
    try {
      set({ validation: await api.validate(get().source), validating: false });
    } catch (err) {
      set({ validating: false, notice: errorNotice(err) });
    }
  },

  deploy: async (expectedHash) => {
    const { draft, dirty, deploying } = get();
    if (!draft || deploying) {
      return;
    }
    // Deploy always ships the saved head — save first if the editor is ahead.
    if (dirty) {
      await get().save("manual", "pre-deploy save");
      if (get().saveConflictHead !== undefined) {
        return;
      }
    }
    const current = get();
    if (!current.draft) {
      return;
    }
    set({ deploying: true, deployConflict: undefined });
    try {
      const result = await api.deploy(
        current.draft.id,
        expectedHash === undefined ? current.liveFileHash : expectedHash,
      );
      set({
        deploying: false,
        liveFileHash: result.file_hash,
        draft: {
          ...current.draft,
          status: "deployed",
          base_file_hash: result.file_hash,
        },
        validation: undefined,
        notice: result.git_error
          ? {
              type: "error",
              text: `Deployed v${result.deployed_version_no}, but git failed: ${result.git_error}`,
            }
          : {
              type: "success",
              text:
                `Deployed v${result.deployed_version_no} to ${current.draft.rel_path}` +
                (result.git_commit_sha
                  ? ` (commit ${result.git_commit_sha.slice(0, 8)}${result.git_pushed ? ", pushed" : ""})`
                  : ""),
            },
      });
      void get().refreshFiles();
    } catch (err) {
      set({ deploying: false });
      if (err instanceof ApiError && err.status === 409) {
        set({ deployConflict: err.detail as DeployConflictDetail });
      } else if (err instanceof ApiError && err.status === 422) {
        const detail = err.detail as { errors?: ValidateResult["errors"] } | undefined;
        set({
          validation: { ok: false, errors: detail?.errors ?? [], dag_count: null },
          notice: { type: "error", text: "Deploy blocked: validation failed" },
        });
      } else {
        set({ notice: errorNotice(err) });
      }
    }
  },

  cancelDeployConflict: () => set({ deployConflict: undefined }),

  toggleHistory: async () => {
    const { showHistory, draft } = get();
    if (showHistory || !draft) {
      set({ showHistory: false });
      return;
    }
    try {
      set({ history: await api.versions(draft.id), showHistory: true });
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  restore: async (versionNo) => {
    const { draft } = get();
    if (!draft) {
      return;
    }
    try {
      await api.restore(draft.id, versionNo);
      await get().reloadDraft();
      set({
        history: await api.versions(draft.id),
        notice: { type: "success", text: `Restored v${versionNo}` },
      });
    } catch (err) {
      set({ notice: errorNotice(err) });
    }
  },

  setNotice: (notice) => set({ notice }),
}));

let regenTimer: number | undefined;

const scheduleRegen = (): void => {
  window.clearTimeout(regenTimer);
  regenTimer = window.setTimeout(() => {
    void regenerateSource();
  }, 400);
};

const regenerateSource = async (): Promise<void> => {
  const { graph, source } = useStore.getState();
  if (!graph) {
    return;
  }
  useStore.setState({ regenerating: true });
  try {
    // Transform mode: minimal edits against the current source (round-trip safe).
    const result = await api.codegen(graph, source || undefined);
    useStore.setState({
      source: result.source,
      dirty: true,
      regenerating: false,
      parseError: undefined,
    });
  } catch (err) {
    // Incomplete graphs (e.g. a required param still empty) are expected while
    // editing — surface quietly, don't toast.
    useStore.setState({
      regenerating: false,
      notice:
        err instanceof ApiError && err.status === 400
          ? { type: "info", text: `Codegen: ${err.message}` }
          : errorNotice(err),
    });
  }
};

let parseTimer: number | undefined;

const scheduleParse = (): void => {
  window.clearTimeout(parseTimer);
  parseTimer = window.setTimeout(() => {
    void parseCurrentSource();
  }, 600);
};

const parseCurrentSource = async (): Promise<void> => {
  const { source, draft } = useStore.getState();
  if (!draft) {
    return;
  }
  try {
    const parsed = await api.parse(source);
    if (useStore.getState().source !== source) {
      return; // stale response — a newer edit is already in flight
    }
    if (parsed.graph) {
      useStore.setState({
        graph: mergePositions(parsed.graph, useStore.getState().graph),
        parseError: undefined,
        parseWarnings: parsed.warnings,
      });
    } else {
      // Keep the last good canvas, mark it frozen.
      useStore.setState({ parseError: parsed.error ?? "Parse failed" });
    }
  } catch (err) {
    useStore.setState({ notice: errorNotice(err) });
  }
};

let autosaveTimer: number | undefined;
let lastAutosaveAt = 0;

export const startAutosave = (): void => {
  if (autosaveTimer !== undefined) {
    return;
  }
  const tick = () => {
    const { config, dirty, draft, saving } = useStore.getState();
    const interval = config?.autosave_interval ?? 0;
    if (
      interval > 0 &&
      dirty &&
      draft &&
      !saving &&
      Date.now() - lastAutosaveAt >= interval * 1000
    ) {
      lastAutosaveAt = Date.now();
      void useStore.getState().save("auto");
    }
  };
  autosaveTimer = window.setInterval(tick, 2000);
};
