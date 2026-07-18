import { beforeEach, describe, expect, it, vi } from "vitest";

// The store schedules a debounced codegen after graph mutations — stub the
// whole API client so nothing hits the network.
vi.mock("src/api/client", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    codegen: vi.fn().mockResolvedValue({ source: "" }),
    parse: vi.fn().mockResolvedValue({ graph: null, warnings: [], error: null }),
    saveVersion: vi.fn().mockResolvedValue({ version_no: 2 }),
    versions: vi.fn().mockResolvedValue([]),
  },
}));

import type { BlockDef, GraphModel } from "src/api/types";
import { useStore } from "./store";

const BLOCKS: BlockDef[] = [
  {
    block_id: "bash",
    label: "Bash",
    category: "Core",
    description: "",
    import_stmt: null,
    params: [{ name: "bash_command", label: "Cmd", type: "text", required: true, default: "echo hi", help: null }],
  },
];

const baseGraph = (): GraphModel => ({
  dag: {
    dag_id: "d",
    schedule: null,
    description: null,
    tags: [],
    start_date: null,
    catchup: null,
    max_active_runs: null,
    owner: null,
    email: null,
    retries: null,
    retry_delay_s: null,
  },
  nodes: [
    { id: "a", block_id: "bash", params: {}, position: { x: 0, y: 0 }, opaque: false, group_id: null },
    { id: "b", block_id: "bash", params: {}, position: { x: 100, y: 0 }, opaque: false, group_id: null },
  ],
  edges: [],
  groups: [],
});

const seed = (graph: GraphModel = baseGraph()) => {
  useStore.setState({ graph, blocks: BLOCKS, dirty: false, selectedNodeId: undefined, multiSelection: [] });
};

const graph = () => useStore.getState().graph!;

describe("addBlock", () => {
  beforeEach(() => seed());

  it("adds a node with a unique id and default params", () => {
    useStore.getState().addBlock("bash");
    const added = graph().nodes.at(-1)!;
    expect(added.block_id).toBe("bash");
    expect(added.id).toBe("bash_1");
    expect(added.params).toEqual({ bash_command: "echo hi" });
    expect(added.opaque).toBe(false);
    expect(useStore.getState().dirty).toBe(true);
  });

  it("honours an explicit drop position", () => {
    useStore.getState().addBlock("bash", { x: 42, y: 7 });
    expect(graph().nodes.at(-1)!.position).toEqual({ x: 42, y: 7 });
  });
});

describe("grouping", () => {
  beforeEach(() => seed());

  it("createGroupWith wraps selected tasks in a new group", () => {
    useStore.getState().createGroupWith(["a", "b"]);
    expect(graph().groups).toEqual([{ id: "group_1", label: "group_1", parent_id: null }]);
    expect(graph().nodes.map((n) => n.group_id)).toEqual(["group_1", "group_1"]);
  });

  it("assignToGroup moves a task in and out of a group", () => {
    useStore.getState().createGroupWith(["a"]);
    useStore.getState().assignToGroup(["b"], "group_1");
    expect(graph().nodes.find((n) => n.id === "b")!.group_id).toBe("group_1");
    useStore.getState().assignToGroup(["b"], null);
    expect(graph().nodes.find((n) => n.id === "b")!.group_id).toBeNull();
  });

  it("renameGroup updates the group id and its members", () => {
    useStore.getState().createGroupWith(["a", "b"]);
    useStore.getState().renameGroup("group_1", "etl");
    expect(graph().groups[0].id).toBe("etl");
    expect(graph().nodes.every((n) => n.group_id === "etl")).toBe(true);
  });

  it("deleteGroup cascades nested groups and lifts members to the parent", () => {
    seed({
      ...baseGraph(),
      groups: [
        { id: "outer", label: "outer", parent_id: null },
        { id: "outer.inner", label: "inner", parent_id: "outer" },
      ],
      nodes: [
        { id: "a", block_id: "bash", params: {}, position: null, opaque: false, group_id: "outer" },
        { id: "b", block_id: "bash", params: {}, position: null, opaque: false, group_id: "outer.inner" },
      ],
    });
    useStore.getState().deleteGroup("outer");
    expect(graph().groups).toEqual([]);
    expect(graph().nodes.every((n) => n.group_id === null)).toBe(true);
  });

  it("moveGroup shifts positions of all members (incl. nested)", () => {
    seed({
      ...baseGraph(),
      groups: [{ id: "g", label: "g", parent_id: null }],
      nodes: [
        { id: "a", block_id: "bash", params: {}, position: { x: 10, y: 10 }, opaque: false, group_id: "g" },
        { id: "b", block_id: "bash", params: {}, position: { x: 20, y: 0 }, opaque: false, group_id: null },
      ],
    });
    useStore.getState().moveGroup("g", 5, -3);
    expect(graph().nodes.find((n) => n.id === "a")!.position).toEqual({ x: 15, y: 7 });
    // non-member untouched
    expect(graph().nodes.find((n) => n.id === "b")!.position).toEqual({ x: 20, y: 0 });
  });
});
