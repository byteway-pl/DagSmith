import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Icon,
  IconButton,
  Input,
  Stack,
  Text,
} from "@chakra-ui/react";
import type { FC } from "react";
import { useMemo, useState } from "react";
import { FiLock, FiUsers } from "react-icons/fi";

import { api } from "src/api/client";
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

export const FileBrowser: FC = () => {
  const bundles = useStore((s) => s.bundles);
  const selectedBundle = useStore((s) => s.selectedBundle);
  const files = useStore((s) => s.files);
  const config = useStore((s) => s.config);
  const teams = useStore((s) => s.teams);
  const selectBundle = useStore((s) => s.selectBundle);
  const openFile = useStore((s) => s.openFile);
  const [newPath, setNewPath] = useState("");
  const [changeTeamFor, setChangeTeamFor] = useState<
    { relPath: string; team: string | null } | undefined
  >();

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

  return (
    <Stack gap={3} h="100%">
      <select
        value={selectedBundle ?? ""}
        onChange={(event) => void selectBundle(event.target.value)}
        style={{
          padding: "6px 8px",
          borderRadius: "6px",
          border: "1px solid var(--chakra-colors-border)",
          background: "transparent",
          width: "100%",
        }}
      >
        {bundles.map((bundle) => (
          <option key={bundle.name} value={bundle.name}>
            {bundle.name}
            {bundle.writable ? "" : " (read-only)"}
          </option>
        ))}
      </select>

      {config?.can_edit ? (
        <HStack>
          <Input
            size="sm"
            placeholder={
              myTeamPrefix ? `${myTeamPrefix}/new_dag.py` : "new/path/dag.py"
            }
            value={newPath}
            onChange={(event) => setNewPath(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                createFile();
              }
            }}
          />
          <Button size="sm" onClick={createFile} disabled={!newPath.trim()}>
            New
          </Button>
        </HStack>
      ) : undefined}

      <Box overflowY="auto" flex="1" borderWidth="1px" borderRadius="md">
        {files.length === 0 ? (
          <Text p={3} color="fg.muted" fontSize="sm">
            No .py files in this bundle yet.
          </Text>
        ) : (
          files.map((file) => (
            <Flex
              key={file.rel_path}
              px={3}
              py={2}
              cursor="pointer"
              _hover={{ bg: "bg.muted" }}
              borderBottomWidth="1px"
              align="center"
              gap={2}
              opacity={file.editable ? 1 : 0.6}
              title={
                file.editable
                  ? undefined
                  : `Managed by team ${file.team} — opens read-only`
              }
              onClick={() => void openFile(file.rel_path, !file.editable)}
            >
              <Text fontSize="sm" fontFamily="mono" truncate flex="1">
                {file.rel_path}
              </Text>
              {file.team ? (
                <Badge colorPalette="teal" size="sm">
                  {file.team}
                </Badge>
              ) : undefined}
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
              {!file.editable ? <Icon as={FiLock} boxSize={3.5} color="fg.muted" /> : undefined}
              {file.has_draft ? (
                <Badge colorPalette="orange" size="sm">
                  draft
                </Badge>
              ) : undefined}
            </Flex>
          ))
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
