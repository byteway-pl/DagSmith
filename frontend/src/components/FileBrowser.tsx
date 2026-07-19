import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Icon,
  IconButton,
  Input,
  InputGroup,
  Stack,
  Text,
} from "@chakra-ui/react";
import type { FC } from "react";
import { useMemo, useState } from "react";
import { FiGrid, FiList, FiLock, FiSearch, FiUser, FiUsers } from "react-icons/fi";

import { api } from "src/api/client";
import type { FileInfo } from "src/api/types";
import { Modal } from "src/components/Modal";
import { useStore } from "src/state/store";

const selectStyle: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: "6px",
  border: "1px solid var(--chakra-colors-border)",
  background: "transparent",
  width: "100%",
  fontSize: "13px",
};

type ViewMode = "cards" | "table";
const VIEW_KEY = "dagsmith:fileView";

const loadView = (): ViewMode =>
  (typeof localStorage !== "undefined" && localStorage.getItem(VIEW_KEY)) === "table"
    ? "table"
    : "cards";

/** Admin-only: assign a DAG file to a team (override) or restore directory rules. */
const ChangeTeamModal: FC<{
  bundle: string;
  relPath: string;
  currentTeam: string | null;
  onClose: () => void;
}> = ({ bundle, relPath, currentTeam, onClose }) => {
  const teams = useStore((s) => s.teams);
  const refreshFiles = useStore((s) => s.refreshFiles);
  const bundleTeams = teams.filter((t) => t.bundle === bundle);
  const [teamId, setTeamId] = useState<string>(
    bundleTeams.find((t) => t.name === currentTeam)?.id ?? "",
  );
  const [error, setError] = useState<string | undefined>();

  const apply = () => {
    api
      .setFileTeam(bundle, relPath, teamId === "" ? null : teamId)
      .then(() => {
        void refreshFiles();
        onClose();
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  };

  return (
    <Modal title="Change team">
      <Stack gap={2}>
        <Text fontSize="sm" fontFamily="mono">
          {relPath}
        </Text>
        <Text fontSize="xs" color="fg.muted">
          Assigns this DAG to a team regardless of its directory. Only members of the
          selected team (and admins) will be able to edit and deploy it. Choosing
          “default” restores directory-based ownership.
        </Text>
        <select value={teamId} style={selectStyle} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">default (by directory)</option>
          {bundleTeams.map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </select>
        {error ? (
          <Text fontSize="xs" color="red.solid">
            {error}
          </Text>
        ) : undefined}
      </Stack>
      <Flex justify="flex-end" gap={2} mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" colorPalette="blue" onClick={apply}>
          Apply
        </Button>
      </Flex>
    </Modal>
  );
};

const StatusBadges: FC<{ file: FileInfo }> = ({ file }) => (
  <>
    {file.team ? (
      <Badge colorPalette="teal" size="sm">
        {file.team}
      </Badge>
    ) : undefined}
    {file.has_draft ? (
      <Badge colorPalette="orange" size="sm">
        draft
      </Badge>
    ) : undefined}
    {!file.deployed ? (
      <Badge
        colorPalette="gray"
        size="sm"
        title="Saved as a draft, never deployed — no file on disk yet"
      >
        not deployed
      </Badge>
    ) : undefined}
    {!file.editable ? <Icon as={FiLock} boxSize={3.5} color="fg.muted" /> : undefined}
  </>
);

export const FileBrowser: FC = () => {
  const bundles = useStore((s) => s.bundles);
  const selectedBundle = useStore((s) => s.selectedBundle);
  const files = useStore((s) => s.files);
  const config = useStore((s) => s.config);
  const teams = useStore((s) => s.teams);
  const selectBundle = useStore((s) => s.selectBundle);
  const openFile = useStore((s) => s.openFile);
  const [newPath, setNewPath] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ViewMode>(loadView);
  const [changeTeamFor, setChangeTeamFor] = useState<
    { relPath: string; team: string | null } | undefined
  >();

  const setViewMode = (mode: ViewMode) => {
    setView(mode);
    try {
      localStorage.setItem(VIEW_KEY, mode);
    } catch {
      /* ignore storage errors */
    }
  };

  // The user's team directory in this bundle — new DAGs land there by default.
  const myTeamPrefix = useMemo(() => {
    const username = config?.username;
    if (!username || !selectedBundle) {
      return "";
    }
    const team = teams.find(
      (t) => t.bundle === selectedBundle && t.members.includes(username),
    );
    return team?.path_prefix ?? "";
  }, [teams, config, selectedBundle]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return files;
    }
    return files.filter((f) => {
      const haystack = [
        f.dag_id ?? "",
        f.rel_path,
        f.description ?? "",
        f.owner ?? "",
        f.created_by ?? "",
        f.team ?? "",
        ...f.tags,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [files, query]);

  const createFile = () => {
    const trimmed = newPath.trim();
    if (!trimmed) {
      return;
    }
    let withExt = trimmed.endsWith(".py") ? trimmed : `${trimmed}.py`;
    // Auto-prefix with the user's team directory unless already targeted there.
    if (myTeamPrefix && !withExt.startsWith(`${myTeamPrefix}/`)) {
      withExt = `${myTeamPrefix}/${withExt}`;
    }
    setNewPath("");
    void openFile(withExt);
  };

  const creator = (f: FileInfo) => f.created_by ?? f.owner;

  return (
    <Stack gap={3} h="100%">
      <Flex gap={2} align="center" wrap="wrap">
        <select
          value={selectedBundle ?? ""}
          onChange={(event) => void selectBundle(event.target.value)}
          style={{ ...selectStyle, width: "auto", minWidth: "160px" }}
        >
          {bundles.map((bundle) => (
            <option key={bundle.name} value={bundle.name}>
              {bundle.name}
              {bundle.writable ? "" : " (read-only)"}
            </option>
          ))}
        </select>

        <InputGroup flex="1" minW="220px" startElement={<Icon as={FiSearch} color="fg.muted" />}>
          <Input
            size="sm"
            placeholder="Search by name, path, tag, owner…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </InputGroup>

        <HStack gap={1}>
          <IconButton
            size="sm"
            aria-label="Card view"
            title="Card view"
            variant={view === "cards" ? "solid" : "outline"}
            onClick={() => setViewMode("cards")}
          >
            <FiGrid />
          </IconButton>
          <IconButton
            size="sm"
            aria-label="Table view"
            title="Table view"
            variant={view === "table" ? "solid" : "outline"}
            onClick={() => setViewMode("table")}
          >
            <FiList />
          </IconButton>
        </HStack>
      </Flex>

      {config?.can_edit ? (
        <HStack>
          <Input
            size="sm"
            placeholder={myTeamPrefix ? `${myTeamPrefix}/new_dag.py` : "new/path/dag.py"}
            value={newPath}
            onChange={(event) => setNewPath(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                createFile();
              }
            }}
          />
          <Button size="sm" onClick={createFile} disabled={!newPath.trim()}>
            New DAG
          </Button>
        </HStack>
      ) : undefined}

      <Box overflowY="auto" flex="1" borderWidth="1px" borderRadius="md">
        {filtered.length === 0 ? (
          <Text p={4} color="fg.muted" fontSize="sm">
            {files.length === 0
              ? "No .py files in this bundle yet."
              : "No DAGs match your search."}
          </Text>
        ) : view === "cards" ? (
          <Stack gap={0}>
            {filtered.map((file) => (
              <Flex
                key={file.rel_path}
                direction="column"
                gap={1}
                px={4}
                py={3}
                cursor="pointer"
                _hover={{ bg: "bg.muted" }}
                borderBottomWidth="1px"
                opacity={file.editable ? 1 : 0.7}
                onClick={() => void openFile(file.rel_path, !file.editable)}
              >
                <Flex align="center" gap={2} wrap="wrap">
                  <Text fontWeight="semibold" fontSize="md" truncate>
                    {file.dag_id ?? file.rel_path.replace(/\.py$/, "")}
                  </Text>
                  <Box flex="1" minW="2" />
                  <StatusBadges file={file} />
                  {config?.is_admin ? (
                    <IconButton
                      size="2xs"
                      variant="ghost"
                      aria-label="Change team"
                      title="Change the owning team of this DAG"
                      onClick={(event) => {
                        event.stopPropagation();
                        setChangeTeamFor({ relPath: file.rel_path, team: file.team });
                      }}
                    >
                      <FiUsers />
                    </IconButton>
                  ) : undefined}
                </Flex>
                <Text fontSize="xs" fontFamily="mono" color="fg.muted" truncate>
                  {file.rel_path}
                </Text>
                {file.description ? (
                  <Text fontSize="sm" color="fg.muted" lineClamp={2}>
                    {file.description}
                  </Text>
                ) : undefined}
                <Flex align="center" gap={2} wrap="wrap" mt={1}>
                  {file.tags.map((tag) => (
                    <Badge key={tag} colorPalette="blue" variant="subtle" size="sm">
                      #{tag}
                    </Badge>
                  ))}
                  <Box flex="1" minW="2" />
                  {creator(file) ? (
                    <HStack gap={1} color="fg.muted">
                      <Icon as={FiUser} boxSize={3.5} />
                      <Text fontSize="xs">{creator(file)}</Text>
                    </HStack>
                  ) : undefined}
                </Flex>
              </Flex>
            ))}
          </Stack>
        ) : (
          <Box>
            <Flex
              px={3}
              py={2}
              borderBottomWidth="1px"
              bg="bg.muted"
              fontSize="xs"
              fontWeight="semibold"
              color="fg.muted"
              textTransform="uppercase"
              gap={3}
            >
              <Box flex="2" minW="0">
                DAG ID / path
              </Box>
              <Box flex="3" minW="0">
                Description
              </Box>
              <Box flex="2" minW="0">
                Tags
              </Box>
              <Box flex="1" minW="0">
                Creator
              </Box>
              <Box w="130px" flexShrink={0}>
                Status
              </Box>
            </Flex>
            {filtered.map((file) => (
              <Flex
                key={file.rel_path}
                px={3}
                py={2}
                gap={3}
                align="center"
                cursor="pointer"
                _hover={{ bg: "bg.muted" }}
                borderBottomWidth="1px"
                opacity={file.editable ? 1 : 0.7}
                onClick={() => void openFile(file.rel_path, !file.editable)}
              >
                <Box flex="2" minW="0">
                  <Text fontSize="sm" fontWeight="medium" truncate>
                    {file.dag_id ?? file.rel_path.replace(/\.py$/, "")}
                  </Text>
                  <Text fontSize="xs" fontFamily="mono" color="fg.muted" truncate>
                    {file.rel_path}
                  </Text>
                </Box>
                <Box flex="3" minW="0">
                  <Text fontSize="sm" color="fg.muted" lineClamp={2}>
                    {file.description ?? "—"}
                  </Text>
                </Box>
                <Flex flex="2" minW="0" gap={1} wrap="wrap">
                  {file.tags.length > 0
                    ? file.tags.map((tag) => (
                        <Badge key={tag} colorPalette="blue" variant="subtle" size="sm">
                          #{tag}
                        </Badge>
                      ))
                    : "—"}
                </Flex>
                <Box flex="1" minW="0">
                  <Text fontSize="xs" color="fg.muted" truncate>
                    {creator(file) ?? "—"}
                  </Text>
                </Box>
                <Flex w="130px" flexShrink={0} gap={1} align="center" wrap="wrap">
                  <StatusBadges file={file} />
                  {config?.is_admin ? (
                    <IconButton
                      size="2xs"
                      variant="ghost"
                      aria-label="Change team"
                      title="Change the owning team of this DAG"
                      onClick={(event) => {
                        event.stopPropagation();
                        setChangeTeamFor({ relPath: file.rel_path, team: file.team });
                      }}
                    >
                      <FiUsers />
                    </IconButton>
                  ) : undefined}
                </Flex>
              </Flex>
            ))}
          </Box>
        )}
      </Box>

      {changeTeamFor && selectedBundle ? (
        <ChangeTeamModal
          bundle={selectedBundle}
          relPath={changeTeamFor.relPath}
          currentTeam={changeTeamFor.team}
          onClose={() => setChangeTeamFor(undefined)}
        />
      ) : undefined}
    </Stack>
  );
};
