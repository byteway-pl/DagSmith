import {
  Box,
  Button,
  Flex,
  HStack,
  IconButton,
  Input,
  Stack,
  Text,
  Textarea,
} from "@chakra-ui/react";
import type { FC } from "react";
import { useState } from "react";
import { FiCode, FiEdit3, FiList, FiSettings } from "react-icons/fi";

import type { BlockParam, GraphModel, TaskNode } from "src/api/types";
import { TRIGGER_RULES } from "src/api/types";
import { DagSettingsModal } from "src/components/DagSettingsModal";
import { parseDictLiteral } from "src/lib/dict";
import { CodeEditorModal, HtmlEditorModal, KeyValueModal } from "src/components/editors";
import { useStore } from "src/state/store";

// Params that typically hold dicts and deserve the key:value editor.
const DICT_PARAM_NAMES = new Set([
  "op_kwargs",
  "params",
  "env",
  "headers",
  "hook_params",
  "templates_dict",
  "conf",
]);

const selectStyle: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: "6px",
  border: "1px solid var(--chakra-colors-border)",
  background: "transparent",
  width: "100%",
  fontSize: "13px",
};

const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

const Field: FC<{ label: string; children: React.ReactNode; help?: string | null }> = ({
  label,
  children,
  help,
}) => (
  <Stack gap={1}>
    <Text fontSize="xs" fontWeight="medium" color="fg.muted">
      {label}
    </Text>
    {children}
    {help ? (
      <Text fontSize="2xs" color="fg.muted">
        {help}
      </Text>
    ) : undefined}
  </Stack>
);

const ExpandableCodeField: FC<{
  param: BlockParam;
  value: string;
  onChange: (value: string) => void;
}> = ({ param, value, onChange }) => {
  const [showCode, setShowCode] = useState(false);
  const [showKv, setShowKv] = useState(false);
  const [showHtml, setShowHtml] = useState(false);
  // Field-type detection (as in the original app): dict-typed params (and
  // python params that hold dict literals) get the key:value editor, params
  // whose name mentions html get the WYSIWYG editor.
  const isDictParam =
    param.type === "dict" ||
    (param.type === "python" &&
      (DICT_PARAM_NAMES.has(param.name) || parseDictLiteral(value) !== null));
  const isHtmlParam = /html/i.test(param.name);

  return (
    <Field label={param.label} help={param.help}>
      <Box position="relative">
        <Textarea
          size="sm"
          fontFamily="mono"
          rows={param.type === "python" ? 5 : 3}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          pr="88px"
        />
        <HStack position="absolute" top={1} right={1} gap={1}>
          {isHtmlParam ? (
            <IconButton
              size="2xs"
              variant="subtle"
              aria-label="WYSIWYG editor"
              title="Open the rich-text (HTML) editor"
              onClick={() => setShowHtml(true)}
            >
              <FiEdit3 />
            </IconButton>
          ) : undefined}
          {isDictParam ? (
            <IconButton
              size="2xs"
              variant="subtle"
              aria-label="Key-value editor"
              title="Edit as key : value"
              onClick={() => setShowKv(true)}
            >
              <FiList />
            </IconButton>
          ) : undefined}
          <IconButton
            size="2xs"
            variant="subtle"
            aria-label="Open code editor"
            title="Open in a large editor"
            onClick={() => setShowCode(true)}
          >
            <FiCode />
          </IconButton>
        </HStack>
      </Box>
      {showCode ? (
        <CodeEditorModal
          title={`Edit ${param.name}`}
          description={param.help}
          value={value}
          onSave={onChange}
          onClose={() => setShowCode(false)}
        />
      ) : undefined}
      {showKv ? (
        <KeyValueModal
          title={`Edit ${param.name}`}
          value={value}
          onSave={onChange}
          onClose={() => setShowKv(false)}
        />
      ) : undefined}
      {showHtml ? (
        <HtmlEditorModal
          title={`Edit ${param.name}`}
          value={value}
          onSave={onChange}
          onClose={() => setShowHtml(false)}
        />
      ) : undefined}
    </Field>
  );
};

const CONN_RE = /(^|_)conn_id$/;

/** conn_id fields: text input with a datalist of known Airflow connections.
 * Free typing stays possible (secrets-backend connections are not listable). */
const ConnField: FC<{
  param: BlockParam;
  value: string;
  onChange: (value: string) => void;
}> = ({ param, value, onChange }) => {
  const connections = useStore((s) => s.connections);
  // e.g. teradata_conn_id -> connections of conn_type "teradata" first
  const typeHint = param.name.replace(/_?conn_id$/, "");
  const sorted = [...connections].sort((a, b) => {
    const aMatch = typeHint !== "" && a.conn_type === typeHint ? 0 : 1;
    const bMatch = typeHint !== "" && b.conn_type === typeHint ? 0 : 1;
    return aMatch - bMatch || a.conn_id.localeCompare(b.conn_id);
  });
  const listId = `dagsmith-conns-${param.name}`;

  return (
    <Field
      label={param.label}
      help={param.help ?? (connections.length === 0 ? "No connections found in Airflow" : null)}
    >
      <Input
        size="sm"
        fontFamily="mono"
        list={listId}
        placeholder={param.default !== null ? String(param.default) : "conn_id…"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <datalist id={listId}>
        {sorted.map((conn) => (
          <option key={conn.conn_id} value={conn.conn_id}>
            {conn.conn_type ?? ""}
          </option>
        ))}
      </datalist>
    </Field>
  );
};

const ParamField: FC<{
  param: BlockParam;
  value: unknown;
  onChange: (value: unknown) => void;
}> = ({ param, value, onChange }) => {
  if (CONN_RE.test(param.name)) {
    return (
      <ConnField param={param} value={String(value ?? "")} onChange={onChange} />
    );
  }
  if (param.name === "trigger_rule") {
    return (
      <Field label={param.label} help={param.help}>
        <select
          value={String(value ?? "")}
          style={selectStyle}
          onChange={(event) => onChange(event.target.value || undefined)}
        >
          <option value="">all_success (default)</option>
          {TRIGGER_RULES.filter((rule) => rule !== "all_success").map((rule) => (
            <option key={rule} value={rule}>
              {rule}
            </option>
          ))}
        </select>
      </Field>
    );
  }
  // HTML-ish params get the rich editor regardless of their declared type
  // (e.g. EmailOperator.html_content is annotated as plain str).
  if (/html/i.test(param.name)) {
    return (
      <ExpandableCodeField param={param} value={String(value ?? "")} onChange={onChange} />
    );
  }
  switch (param.type) {
    case "text":
    case "python":
    case "dict":
      return (
        <ExpandableCodeField
          param={param}
          value={String(value ?? "")}
          onChange={onChange}
        />
      );
    case "int":
      return (
        <Field label={param.label} help={param.help}>
          <Input
            size="sm"
            type="number"
            value={value === undefined || value === null ? "" : String(value)}
            onChange={(event) =>
              onChange(event.target.value === "" ? undefined : Number(event.target.value))
            }
          />
        </Field>
      );
    case "bool":
      return (
        <Field label={param.label} help={param.help}>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) => onChange(event.target.checked)}
          />
        </Field>
      );
    default:
      return (
        <Field label={param.label} help={param.help}>
          <Input
            size="sm"
            value={String(value ?? "")}
            onChange={(event) => onChange(event.target.value)}
          />
        </Field>
      );
  }
};

const GroupField: FC<{ node: TaskNode }> = ({ node }) => {
  const graph = useStore((s) => s.graph);
  const { mutateGraph } = useStore.getState();
  const [creating, setCreating] = useState(false);
  const [newGroupId, setNewGroupId] = useState("");

  if (!graph) {
    return null;
  }

  const setGroup = (groupId: string | null) => {
    mutateGraph((g) => ({
      ...g,
      nodes: g.nodes.map((n) => (n.id === node.id ? { ...n, group_id: groupId } : n)),
    }));
  };

  const createAndAssign = () => {
    const groupId = newGroupId.trim();
    if (!IDENT_RE.test(groupId)) {
      return;
    }
    mutateGraph((g) => ({
      ...g,
      groups: g.groups.some((existing) => existing.id === groupId)
        ? g.groups
        : [...g.groups, { id: groupId, label: groupId, parent_id: null }],
      nodes: g.nodes.map((n) => (n.id === node.id ? { ...n, group_id: groupId } : n)),
    }));
    setCreating(false);
    setNewGroupId("");
  };

  return (
    <Field label="Task group">
      <select
        value={creating ? "__new__" : (node.group_id ?? "")}
        style={selectStyle}
        onChange={(event) => {
          const value = event.target.value;
          if (value === "__new__") {
            setCreating(true);
          } else {
            setCreating(false);
            setGroup(value === "" ? null : value);
          }
        }}
      >
        <option value="">(no group)</option>
        {graph.groups.map((group) => (
          <option key={group.id} value={group.id}>
            {group.id}
          </option>
        ))}
        <option value="__new__">+ new group…</option>
      </select>
      {creating ? (
        <HStack mt={1}>
          <Input
            size="sm"
            fontFamily="mono"
            placeholder="group_id"
            value={newGroupId}
            onChange={(event) => setNewGroupId(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                createAndAssign();
              }
            }}
          />
          <Button size="sm" onClick={createAndAssign} disabled={!IDENT_RE.test(newGroupId.trim())}>
            Create
          </Button>
        </HStack>
      ) : undefined}
    </Field>
  );
};

const NodeInspector: FC<{ node: TaskNode }> = ({ node }) => {
  const blocks = useStore((s) => s.blocks);
  const { mutateGraph, selectNode } = useStore.getState();
  const block = blocks.find((b) => b.block_id === node.block_id);

  if (node.opaque) {
    return (
      <Stack gap={3}>
        <Text fontWeight="bold" fontSize="sm">
          Code-only task
        </Text>
        <Text fontSize="xs" color="fg.muted">
          This task uses a construct DagSmith cannot edit visually. Edit it in the
          Code view; you can still connect or delete it here.
        </Text>
        <Textarea
          size="sm"
          fontFamily="mono"
          rows={6}
          readOnly
          value={String(node.params.code ?? "")}
        />
        <Button
          size="xs"
          colorPalette="red"
          variant="outline"
          onClick={() => {
            mutateGraph((graph) => ({
              ...graph,
              nodes: graph.nodes.filter((n) => n.id !== node.id),
              edges: graph.edges.filter(
                (edge) => edge.source !== node.id && edge.target !== node.id,
              ),
            }));
            selectNode(undefined);
          }}
        >
          Delete task
        </Button>
      </Stack>
    );
  }

  const rename = (newId: string) => {
    if (!IDENT_RE.test(newId) || newId === node.id) {
      return;
    }
    mutateGraph((graph) => {
      if (graph.nodes.some((n) => n.id === newId)) {
        return graph;
      }
      selectNode(newId);
      return {
        ...graph,
        nodes: graph.nodes.map((n) => (n.id === node.id ? { ...n, id: newId } : n)),
        edges: graph.edges.map((edge) => ({
          source: edge.source === node.id ? newId : edge.source,
          target: edge.target === node.id ? newId : edge.target,
          label: edge.label,
        })),
      };
    });
  };

  const setParam = (name: string, value: unknown) => {
    mutateGraph((graph) => ({
      ...graph,
      nodes: graph.nodes.map((n) =>
        n.id === node.id ? { ...n, params: { ...n.params, [name]: value } } : n,
      ),
    }));
  };

  return (
    <Stack gap={3}>
      <Text fontWeight="bold" fontSize="sm">
        {block?.label ?? node.block_id} task
        {node.group_id ? ` · group: ${node.group_id}` : ""}
      </Text>
      <Field label="Task id">
        <Input
          size="sm"
          fontFamily="mono"
          defaultValue={node.id}
          key={node.id}
          onBlur={(event) => rename(event.target.value.trim())}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              rename((event.target as HTMLInputElement).value.trim());
            }
          }}
        />
      </Field>
      <GroupField node={node} />
      {(block?.params ?? []).map((param) => (
        <ParamField
          key={param.name}
          param={param}
          value={node.params[param.name]}
          onChange={(value) => setParam(param.name, value)}
        />
      ))}
      <Button
        size="xs"
        colorPalette="red"
        variant="outline"
        onClick={() => {
          mutateGraph((graph) => ({
            ...graph,
            nodes: graph.nodes.filter((n) => n.id !== node.id),
            edges: graph.edges.filter(
              (edge) => edge.source !== node.id && edge.target !== node.id,
            ),
          }));
          selectNode(undefined);
        }}
      >
        Delete task
      </Button>
    </Stack>
  );
};

const DagInspector: FC<{ graph: GraphModel }> = ({ graph }) => {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <Flex direction="column" align="center" justify="center" h="100%" gap={3} px={4}>
      <Box
        as="button"
        onClick={() => setShowSettings(true)}
        title="Open DAG settings"
        cursor="pointer"
        p={5}
        borderRadius="full"
        borderWidth="1px"
        color="fg.muted"
        css={{
          transition: "all 0.25s ease",
          "& svg": { transition: "transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)" },
          "&:hover": {
            color: "var(--chakra-colors-blue-solid)",
            borderColor: "var(--chakra-colors-blue-solid)",
            boxShadow: "0 0 24px rgba(59, 130, 246, 0.35)",
          },
          "&:hover svg": { transform: "rotate(180deg) scale(1.15)" },
        }}
      >
        <FiSettings size={40} />
      </Box>
      <Text fontWeight="bold" fontFamily="mono" fontSize="sm" textAlign="center">
        {graph.dag.dag_id}
      </Text>
      <Text fontSize="xs" color="fg.muted" textAlign="center">
        {graph.dag.schedule ?? "no schedule"}
        {graph.dag.start_date ? ` · from ${graph.dag.start_date}` : ""}
      </Text>
      <Text fontSize="2xs" color="fg.muted" textAlign="center">
        Click the gear for DAG settings (schedule, start date, default args). Click a
        task to edit its parameters, click an arrow to set its label and trigger rule.
      </Text>
      {showSettings ? <DagSettingsModal onClose={() => setShowSettings(false)} /> : undefined}
    </Flex>
  );
};

export const Inspector: FC = () => {
  const graph = useStore((s) => s.graph);
  const selectedNodeId = useStore((s) => s.selectedNodeId);

  if (!graph) {
    return null;
  }
  const node = graph.nodes.find((n) => n.id === selectedNodeId);

  return (
    <Stack p={3} overflowY="auto" h="100%">
      {node ? <NodeInspector node={node} /> : <DagInspector graph={graph} />}
    </Stack>
  );
};
