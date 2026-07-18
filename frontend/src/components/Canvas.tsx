import { Box, Button, Flex, Input, Stack, Text } from "@chakra-ui/react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ViewportPortal,
  type Connection,
  type Edge as RFEdge,
  type Node as RFNode,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { DragEvent, FC } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiFolder } from "react-icons/fi";

import type { GraphModel } from "src/api/types";
import { blockIcon } from "src/components/blockIcons";
import { EdgeModal } from "src/components/EdgeModal";
import { Modal } from "src/components/Modal";
import { DRAG_MIME } from "src/components/Palette";
import { useStore } from "src/state/store";

// Visual language ported from the original standalone DagSmith app:
// dark slate canvas, horizontal task cards with a typed icon square,
// smoothstep edges with arrowheads, blue selection glow, dashed group frames.
const C = {
  canvas: "#0f172a",
  dots: "#475569",
  card: "#0f172a",
  cardSelected: "#1e293b",
  border: "#475569",
  borderSelected: "#3b82f6",
  iconBox: "#1e293b",
  iconBoxBorder: "#334155",
  handle: "#64748b",
  handleSelected: "#3b82f6",
  edge: "#64748b",
  subText: "#64748b",
  subTextSelected: "#60a5fa",
  groupText: "#93c5fd",
  groupFrame: "#93c5fd",
};

// Estimated card size used for group frames and drop-into-frame hit tests
// (React Flow measures nodes lazily; estimates are close enough here).
const NODE_W = 240;
const NODE_H = 78;

type TaskNodeData = {
  taskId: string;
  blockId: string;
  blockLabel: string;
  category: string;
  selected: boolean;
  opaque: boolean;
  groupId: string | null;
};
type TaskRFNode = RFNode<TaskNodeData, "task">;

const handleStyle = (selected: boolean, side: "left" | "right") => ({
  width: 12,
  height: 12,
  borderRadius: "50%",
  border: "2px solid #0f172a",
  background: selected ? C.handleSelected : C.handle,
  [side]: -6,
});

const TaskNodeView: FC<NodeProps<TaskRFNode>> = ({ data }) => {
  const { Icon: NodeIcon, color: iconColor } = blockIcon(
    data.blockId,
    data.blockLabel,
    data.category,
    data.opaque,
  );

  return (
    <Flex
      align="center"
      minW="200px"
      maxW="280px"
      p={3}
      borderRadius="lg"
      bg={data.selected ? C.cardSelected : C.card}
      borderWidth={data.selected ? "2px" : "1px"}
      borderStyle={data.opaque ? "dashed" : "solid"}
      borderColor={data.selected ? C.borderSelected : C.border}
      boxShadow={data.selected ? "0 8px 24px rgba(30, 64, 175, 0.35)" : "0 4px 12px rgba(0,0,0,0.4)"}
      opacity={data.selected ? 1 : 0.9}
      transition="all 0.15s"
      _hover={{ borderColor: C.borderSelected, opacity: 1 }}
      cursor="pointer"
    >
      <Handle type="target" position={Position.Left} style={handleStyle(data.selected, "left")} />

      <Flex
        w="40px"
        h="40px"
        flexShrink={0}
        align="center"
        justify="center"
        borderRadius="md"
        bg={C.iconBox}
        borderWidth="1px"
        borderColor={C.iconBoxBorder}
        mr={3}
      >
        <NodeIcon size={20} color={iconColor} />
      </Flex>

      <Box flex="1" minW="0">
        <Text fontSize="sm" fontWeight="bold" color="white" lineHeight="tight" wordBreak="break-word">
          {data.taskId}
        </Text>
        <Text
          fontSize="10px"
          textTransform="uppercase"
          letterSpacing="wider"
          color={data.selected ? C.subTextSelected : C.subText}
          truncate
          title={data.blockLabel}
        >
          {data.opaque ? "code-only" : data.blockLabel}
        </Text>
      </Box>

      <Handle type="source" position={Position.Right} style={handleStyle(data.selected, "right")} />
    </Flex>
  );
};

// A group's connection surface: an invisible full-frame RF node whose only
// interactive parts are the left (target) and right (source) handles, so a
// TaskGroup can be a dependency endpoint (`task >> group`, `group >> task`).
type GroupNodeData = { groupId: string };
type GroupRFNode = RFNode<GroupNodeData, "group">;

const groupHandleStyle = {
  width: 14,
  height: 14,
  borderRadius: "50%",
  border: "2px solid #0f172a",
  background: C.groupFrame,
  pointerEvents: "all" as const,
};

const GroupHandleNode: FC<NodeProps<GroupRFNode>> = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ ...groupHandleStyle, left: -7 }} />
    <Handle type="source" position={Position.Right} style={{ ...groupHandleStyle, right: -7 }} />
  </>
);

const nodeTypes = { task: TaskNodeView, group: GroupHandleNode };

const toRfNodes = (
  graph: GraphModel,
  blockInfo: Map<string, { label: string; category: string }>,
  selectedIds: Set<string>,
): TaskRFNode[] =>
  graph.nodes.map((node, index) => {
    const info = blockInfo.get(node.block_id);
    return {
      id: node.id,
      type: "task",
      position:
        node.position ?? { x: 80 + (index % 3) * 280, y: 60 + Math.floor(index / 3) * 130 },
      selected: selectedIds.has(node.id),
      data: {
        taskId: node.id,
        blockId: node.block_id,
        blockLabel: info?.label ?? node.block_id.split(".").pop() ?? node.block_id,
        category: info?.category ?? "",
        selected: selectedIds.has(node.id),
        opaque: node.opaque,
        groupId: node.group_id,
      },
    };
  });

const toRfEdges = (graph: GraphModel): RFEdge[] =>
  graph.edges.map((edge) => ({
    id: `${edge.source}->${edge.target}`,
    source: edge.source,
    target: edge.target,
    label: edge.label ?? undefined,
    labelStyle: { fill: "#93c5fd", fontSize: 11, fontWeight: 600 },
    labelBgStyle: { fill: "#1e293b", stroke: "#334155" },
    labelBgPadding: [6, 3] as [number, number],
    labelBgBorderRadius: 6,
  }));

type Frame = {
  groupId: string;
  depth: number;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** Dashed group frames derived from member-node positions (nested included). */
const computeFrames = (graph: GraphModel): Frame[] => {
  const frames: Frame[] = [];
  for (const group of graph.groups) {
    const members = graph.nodes.filter(
      (n) => n.group_id === group.id || (n.group_id ?? "").startsWith(`${group.id}.`),
    );
    if (members.length === 0) {
      continue;
    }
    const depth = group.id.split(".").length - 1;
    const pad = 28 + (2 - Math.min(depth, 2)) * 8;
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    members.forEach((node, index) => {
      const pos = node.position ?? { x: 80 + (index % 3) * 280, y: 60 + index * 130 };
      minX = Math.min(minX, pos.x);
      minY = Math.min(minY, pos.y);
      maxX = Math.max(maxX, pos.x + NODE_W);
      maxY = Math.max(maxY, pos.y + NODE_H);
    });
    frames.push({
      groupId: group.id,
      depth,
      x: minX - pad,
      y: minY - pad - 26,
      w: maxX - minX + pad * 2,
      h: maxY - minY + pad * 2 + 26,
    });
  }
  return frames.sort((a, b) => a.depth - b.depth);
};

type Menu = { x: number; y: number; nodeIds: string[] };

const GroupEditModal: FC<{ groupId: string; onClose: () => void }> = ({ groupId, onClose }) => {
  const graph = useStore((s) => s.graph);
  const { renameGroup, deleteGroup } = useStore.getState();
  const group = graph?.groups.find((g) => g.id === groupId);
  const [name, setName] = useState(group?.label ?? groupId.split(".").pop() ?? "");
  const [confirming, setConfirming] = useState(false);

  if (!graph || !group) {
    return null;
  }
  const inSubtree = (id: string | null) =>
    id !== null && (id === groupId || id.startsWith(`${groupId}.`));
  const hasChildren = graph.groups.some((g) => g.parent_id === groupId);
  const members = graph.nodes.filter((n) => inSubtree(n.group_id));
  const opaqueMembers = members.filter((n) => n.opaque);
  const nestedCount = graph.groups.filter((g) => g.id !== groupId && inSubtree(g.id)).length;
  const localValid = /^[A-Za-z_][A-Za-z0-9_]*$/.test(name.trim());
  const currentLocal = group.label ?? groupId.split(".").pop();

  return (
    <Modal title={`Group: ${groupId}`}>
      <Stack gap={4}>
        <Stack gap={1}>
          <Text fontSize="xs" fontWeight="medium" color="fg.muted">
            Group id
          </Text>
          <Flex gap={2}>
            <Input
              size="sm"
              fontFamily="mono"
              value={name}
              disabled={hasChildren}
              onChange={(event) => setName(event.target.value)}
            />
            <Button
              size="sm"
              disabled={hasChildren || !localValid || name.trim() === currentLocal}
              onClick={() => {
                renameGroup(groupId, name.trim());
                onClose();
              }}
            >
              Rename
            </Button>
          </Flex>
          {hasChildren ? (
            <Text fontSize="2xs" color="fg.muted">
              Groups containing nested groups can be renamed only in the Code view.
            </Text>
          ) : undefined}
        </Stack>

        <Stack gap={2}>
          <Text fontSize="xs" fontWeight="medium" color="fg.muted">
            Danger zone
          </Text>
          {opaqueMembers.length > 0 ? (
            <Text fontSize="xs" color="orange.solid">
              This group contains {opaqueMembers.length} code-only block(s) — delete it in
              the Code view.
            </Text>
          ) : confirming ? (
            <>
              <Text fontSize="sm">
                This will ungroup <b>{members.length}</b> task(s)
                {nestedCount > 0 ? (
                  <>
                    {" "}
                    and remove <b>{nestedCount}</b> nested group(s)
                  </>
                ) : undefined}
                . The tasks stay in the DAG; the <code>with TaskGroup(…)</code> block is
                removed from the code. Are you sure?
              </Text>
              <Flex gap={2}>
                <Button size="sm" variant="outline" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  colorPalette="red"
                  onClick={() => {
                    deleteGroup(groupId);
                    onClose();
                  }}
                >
                  Delete group
                </Button>
              </Flex>
            </>
          ) : (
            <Button
              size="sm"
              variant="outline"
              colorPalette="red"
              alignSelf="flex-start"
              onClick={() => setConfirming(true)}
            >
              Delete group…
            </Button>
          )}
        </Stack>
      </Stack>
      <Flex justify="flex-end" mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      </Flex>
    </Modal>
  );
};

export const Canvas: FC = () => {
  const graph = useStore((s) => s.graph);
  const blocks = useStore((s) => s.blocks);
  const selectedNodeId = useStore((s) => s.selectedNodeId);
  const multiSelection = useStore((s) => s.multiSelection);
  const {
    mutateGraph,
    selectNode,
    setMultiSelection,
    addBlock,
    assignToGroup,
    createGroupWith,
    moveGroup,
  } = useStore.getState();
  const flowInstance = useRef<ReactFlowInstance<RFNode, RFEdge> | null>(null);
  const [menu, setMenu] = useState<Menu | undefined>();
  const [editGroup, setEditGroup] = useState<string | undefined>();
  const [editEdge, setEditEdge] = useState<{ source: string; target: string } | undefined>();
  const frameDrag = useRef<{
    groupId: string;
    lastX: number;
    lastY: number;
    travelled: number;
  } | null>(null);

  const onFrameHeaderMouseDown = useCallback(
    (event: React.MouseEvent, groupId: string) => {
      event.preventDefault();
      event.stopPropagation();
      frameDrag.current = {
        groupId,
        lastX: event.clientX,
        lastY: event.clientY,
        travelled: 0,
      };
      const onMove = (move: MouseEvent) => {
        const drag = frameDrag.current;
        if (!drag) {
          return;
        }
        const zoom = flowInstance.current?.getViewport().zoom ?? 1;
        const dxScreen = move.clientX - drag.lastX;
        const dyScreen = move.clientY - drag.lastY;
        drag.lastX = move.clientX;
        drag.lastY = move.clientY;
        drag.travelled += Math.abs(dxScreen) + Math.abs(dyScreen);
        moveGroup(drag.groupId, dxScreen / zoom, dyScreen / zoom);
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        const drag = frameDrag.current;
        frameDrag.current = null;
        if (drag && drag.travelled < 4) {
          setEditGroup(drag.groupId);
        }
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [moveGroup],
  );

  const blockInfo = useMemo(
    () =>
      new Map(
        blocks.map((block) => [
          block.block_id,
          { label: block.label, category: block.category },
        ]),
      ),
    [blocks],
  );

  const selectedIds = useMemo(() => {
    const ids = new Set(multiSelection);
    if (selectedNodeId) {
      ids.add(selectedNodeId);
    }
    return ids;
  }, [multiSelection, selectedNodeId]);

  const frames = useMemo(() => (graph ? computeFrames(graph) : []), [graph]);
  const nodes = useMemo<RFNode[]>(() => {
    if (!graph) {
      return [];
    }
    const taskNodes = toRfNodes(graph, blockInfo, selectedIds);
    // Group handle nodes first so they render behind the task cards.
    const groupNodes: GroupRFNode[] = frames.map((frame) => ({
      id: frame.groupId,
      type: "group",
      position: { x: frame.x, y: frame.y },
      data: { groupId: frame.groupId },
      draggable: false,
      selectable: false,
      connectable: true,
      style: { width: frame.w, height: frame.h, pointerEvents: "none" },
      zIndex: 0,
    }));
    return [...groupNodes, ...taskNodes];
  }, [graph, blockInfo, selectedIds, frames]);
  const edges = useMemo(() => (graph ? toRfEdges(graph) : []), [graph]);

  const deleteNodes = useCallback(
    (ids: string[]) => {
      const toDelete = new Set(ids);
      mutateGraph((g) => ({
        ...g,
        nodes: g.nodes.filter((node) => !toDelete.has(node.id)),
        edges: g.edges.filter(
          (edge) => !toDelete.has(edge.source) && !toDelete.has(edge.target),
        ),
      }));
      selectNode(undefined);
      setMultiSelection([]);
    },
    [mutateGraph, selectNode, setMultiSelection],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const selection = new Set(useStore.getState().multiSelection);
      let selectionChanged = false;
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          const { id } = change;
          const position = change.position;
          mutateGraph(
            (g) => ({
              ...g,
              nodes: g.nodes.map((node) =>
                node.id === id ? { ...node, position: { x: position.x, y: position.y } } : node,
              ),
            }),
            true, // position-only: no codegen needed
          );
        } else if (change.type === "remove") {
          deleteNodes([change.id]);
        } else if (change.type === "select") {
          selectionChanged = true;
          if (change.selected) {
            selection.add(change.id);
          } else {
            selection.delete(change.id);
          }
        }
      }
      if (selectionChanged) {
        setMultiSelection([...selection]);
      }
    },
    [mutateGraph, deleteNodes, setMultiSelection],
  );

  const onEdgesChange = useCallback(
    (changes: { type: string; id?: string }[]) => {
      for (const change of changes) {
        if (change.type === "remove" && change.id) {
          const edgeId = change.id;
          mutateGraph((g) => ({
            ...g,
            edges: g.edges.filter((edge) => `${edge.source}->${edge.target}` !== edgeId),
          }));
        }
      }
    },
    [mutateGraph],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const { source, target } = connection;
      if (!source || !target || source === target) {
        return;
      }
      const g = useStore.getState().graph;
      if (!g) {
        return;
      }
      // Reject connecting a group to a task that lives inside it (self-dep).
      const groupIds = new Set(g.groups.map((gr) => gr.id));
      const taskGroup = (id: string) => g.nodes.find((n) => n.id === id)?.group_id ?? null;
      const contains = (groupId: string, taskId: string) => {
        const m = taskGroup(taskId);
        return m !== null && (m === groupId || m.startsWith(`${groupId}.`));
      };
      if (groupIds.has(source) && !groupIds.has(target) && contains(source, target)) {
        return;
      }
      if (groupIds.has(target) && !groupIds.has(source) && contains(target, source)) {
        return;
      }
      mutateGraph((current) =>
        current.edges.some((edge) => edge.source === source && edge.target === target)
          ? current
          : { ...current, edges: [...current.edges, { source, target, label: null }] },
      );
    },
    [mutateGraph],
  );

  const onDragOver = useCallback((event: DragEvent) => {
    if (event.dataTransfer.types.includes(DRAG_MIME)) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    }
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      const blockId = event.dataTransfer.getData(DRAG_MIME);
      if (!blockId || !flowInstance.current) {
        return;
      }
      event.preventDefault();
      const dropPoint = flowInstance.current.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      // Center the new card roughly under the cursor.
      addBlock(blockId, { x: dropPoint.x - 110, y: dropPoint.y - 35 });
    },
    [addBlock],
  );

  // Dropping a card inside a group frame joins that group (deepest frame wins).
  const onNodeDragStop = useCallback(
    (_event: unknown, node: RFNode) => {
      if (node.type === "group") {
        return;
      }
      const centerX = node.position.x + NODE_W / 2;
      const centerY = node.position.y + NODE_H / 2;
      const hit = [...frames]
        .reverse() // deepest frames last in render order
        .find(
          (frame) =>
            centerX >= frame.x &&
            centerX <= frame.x + frame.w &&
            centerY >= frame.y &&
            centerY <= frame.y + frame.h,
        );
      const current = useStore.getState().graph?.nodes.find((n) => n.id === node.id);
      if (hit && current && current.group_id !== hit.groupId && !current.opaque) {
        assignToGroup([node.id], hit.groupId);
      }
    },
    [frames, assignToGroup],
  );

  const openMenu = useCallback(
    (event: React.MouseEvent, nodeIds: string[]) => {
      event.preventDefault();
      setMenu({ x: event.clientX, y: event.clientY, nodeIds });
    },
    [],
  );

  // Ctrl/Cmd+G groups the current selection.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable) {
        return;
      }
      if (event.key === "g" && (event.metaKey || event.ctrlKey)) {
        const ids = [...useStore.getState().multiSelection];
        if (ids.length > 0) {
          event.preventDefault();
          createGroupWith(ids);
        }
      }
    };
    window.addEventListener("keydown", onKey, { capture: true });
    return () => window.removeEventListener("keydown", onKey, { capture: true });
  }, [createGroupWith]);

  if (!graph) {
    return null;
  }

  const menuHasGrouped =
    menu !== undefined &&
    graph.nodes.some((n) => menu.nodeIds.includes(n.id) && n.group_id !== null);

  return (
    <Box
      h="100%"
      w="100%"
      position="relative"
      css={{
        "& .react-flow__controls": {
          background: C.cardSelected,
          border: `1px solid ${C.iconBoxBorder}`,
          borderRadius: "8px",
          overflow: "hidden",
          boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
        },
        "& .react-flow__controls-button": {
          background: C.cardSelected,
          borderBottom: `1px solid ${C.iconBoxBorder}`,
          color: "#94a3b8",
        },
        "& .react-flow__controls-button:hover": {
          background: C.iconBoxBorder,
          color: "white",
        },
        "& .react-flow__controls-button svg": {
          fill: "currentColor",
        },
        "& .react-flow__edge.selected .react-flow__edge-path": {
          stroke: C.borderSelected,
        },
        "& .react-flow__selection": {
          background: "rgba(59, 130, 246, 0.08)",
          border: `1px dashed ${C.borderSelected}`,
        },
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_event, node) => selectNode(node.id)}
        onEdgeClick={(_event, edge) =>
          setEditEdge({ source: edge.source, target: edge.target })
        }
        onPaneClick={() => {
          selectNode(undefined);
          setMultiSelection([]);
          setMenu(undefined);
        }}
        onNodeContextMenu={(event, node) => {
          const selection = useStore.getState().multiSelection;
          openMenu(event, selection.includes(node.id) ? selection : [node.id]);
        }}
        onSelectionContextMenu={(event, selectionNodes) =>
          openMenu(event, selectionNodes.map((n) => n.id))
        }
        onPaneContextMenu={(event) => {
          event.preventDefault();
          setMenu(undefined);
        }}
        onNodeDragStop={onNodeDragStop}
        onInit={(instance) => {
          flowInstance.current = instance;
        }}
        onDragOver={onDragOver}
        onDrop={onDrop}
        fitView
        deleteKeyCode={["Backspace", "Delete"]}
        selectionKeyCode="Shift"
        multiSelectionKeyCode={["Meta", "Control"]}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: { stroke: C.edge, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: C.edge },
        }}
        connectionLineStyle={{ stroke: C.borderSelected, strokeWidth: 2 }}
        style={{ backgroundColor: C.canvas }}
      >
        <ViewportPortal>
          {frames.map((frame) => (
            <Box
              key={frame.groupId}
              position="absolute"
              style={{
                transform: `translate(${frame.x}px, ${frame.y}px)`,
                width: frame.w,
                height: frame.h,
              }}
              border={`2px dashed ${C.groupFrame}`}
              borderRadius="12px"
              bg="rgba(59, 130, 246, 0.05)"
              pointerEvents="none"
              zIndex={-1}
            >
              <Flex
                align="center"
                gap={1.5}
                px={3}
                py={1}
                display="inline-flex"
                pointerEvents="all"
                cursor="grab"
                _active={{ cursor: "grabbing" }}
                _hover={{ bg: "rgba(59, 130, 246, 0.15)" }}
                borderRadius="10px"
                title="Drag to move the group · click to rename or delete"
                onMouseDown={(event) => onFrameHeaderMouseDown(event, frame.groupId)}
              >
                <FiFolder size={13} color={C.groupFrame} />
                <Text fontSize="xs" fontWeight="bold" color={C.groupFrame} userSelect="none">
                  {frame.groupId}
                </Text>
              </Flex>
            </Box>
          ))}
        </ViewportPortal>
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1.2}
          color={C.dots}
          style={{ backgroundColor: C.canvas }}
        />
        <Controls />
        <MiniMap
          pannable
          zoomable
          style={{
            backgroundColor: C.cardSelected,
            border: `1px solid ${C.iconBoxBorder}`,
            borderRadius: 8,
          }}
          nodeColor={C.border}
          maskColor="rgba(15, 23, 42, 0.7)"
        />
      </ReactFlow>

      {editGroup ? (
        <GroupEditModal groupId={editGroup} onClose={() => setEditGroup(undefined)} />
      ) : undefined}

      {editEdge ? (
        <EdgeModal
          source={editEdge.source}
          target={editEdge.target}
          onClose={() => setEditEdge(undefined)}
        />
      ) : undefined}

      {menu ? (
        <Box
          position="fixed"
          left={menu.x}
          top={menu.y}
          zIndex={1500}
          bg={C.cardSelected}
          borderWidth="1px"
          borderColor={C.iconBoxBorder}
          borderRadius="md"
          boxShadow="0 8px 24px rgba(0,0,0,0.5)"
          py={1}
          minW="180px"
          onMouseLeave={() => setMenu(undefined)}
        >
          {[
            {
              label: `Group ${menu.nodeIds.length} task${menu.nodeIds.length > 1 ? "s" : ""}`,
              hint: "⌘G",
              action: () => createGroupWith(menu.nodeIds),
              show: true,
            },
            {
              label: "Ungroup",
              hint: "",
              action: () => assignToGroup(menu.nodeIds, null),
              show: menuHasGrouped,
            },
            {
              label: `Delete ${menu.nodeIds.length > 1 ? `${menu.nodeIds.length} tasks` : "task"}`,
              hint: "⌫",
              action: () => deleteNodes(menu.nodeIds),
              show: true,
            },
          ]
            .filter((item) => item.show)
            .map((item) => (
              <Flex
                key={item.label}
                px={3}
                py={1.5}
                gap={4}
                justify="space-between"
                cursor="pointer"
                color="#e2e8f0"
                fontSize="sm"
                _hover={{ bg: C.iconBoxBorder }}
                onClick={() => {
                  item.action();
                  setMenu(undefined);
                }}
              >
                <Text>{item.label}</Text>
                <Text color={C.subText}>{item.hint}</Text>
              </Flex>
            ))}
        </Box>
      ) : undefined}
    </Box>
  );
};
