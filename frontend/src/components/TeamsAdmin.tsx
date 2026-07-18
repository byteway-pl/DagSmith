import {
  Badge,
  Box,
  Button,
  Flex,
  Grid,
  IconButton,
  Input,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react";
import type { FC } from "react";
import { useEffect, useState } from "react";
import { FiEdit2, FiGitBranch, FiPlus, FiTrash2, FiUsers } from "react-icons/fi";

import { api } from "src/api/client";
import type { BundleInfo, TeamInfo } from "src/api/types";
import { Modal } from "src/components/Modal";
import { useStore } from "src/state/store";

const FieldLabel: FC<{ children: React.ReactNode }> = ({ children }) => (
  <Text fontSize="2xs" fontWeight="bold" color="fg.muted" letterSpacing="wider" mb={0.5}>
    {children}
  </Text>
);

const selectStyle: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: "6px",
  border: "1px solid var(--chakra-colors-border)",
  background: "transparent",
  fontSize: "13px",
  width: "100%",
};

const TeamCard: FC<{
  team: TeamInfo;
  bundles: BundleInfo[];
  onChanged: () => void;
}> = ({ team, bundles, onChanged }) => {
  const [newMember, setNewMember] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState({
    name: team.name,
    bundle: team.bundle,
    path_prefix: team.path_prefix,
    git_remote_url: team.git_remote_url ?? "",
    git_branch: team.git_branch,
    git_push: team.git_push,
  });
  const bundleGit = bundles.find((b) => b.name === team.bundle)?.git ?? false;

  const addMember = () => {
    const username = newMember.trim();
    if (!username) {
      return;
    }
    setNewMember("");
    void api.addTeamMember(team.id, username).then(onChanged);
  };

  const saveEdit = () => {
    void api
      .updateTeam(team.id, {
        name: edit.name.trim(),
        description: team.description,
        bundle: edit.bundle,
        path_prefix: edit.path_prefix.trim().replace(/^\/+|\/+$/g, ""),
        git_remote_url: edit.git_remote_url.trim() || null,
        git_branch: edit.git_branch.trim() || "main",
        git_push: edit.git_push,
      })
      .then(() => {
        setEditing(false);
        onChanged();
      });
  };

  if (editing) {
    return (
      <Box borderWidth="1px" borderColor="blue.solid" borderRadius="md" p={3}>
        <Text fontSize="xs" fontWeight="bold" mb={2}>
          Edit team: {team.name}
        </Text>
        <Grid templateColumns="1fr 1fr" gap={2}>
          <Box>
            <FieldLabel>TEAM NAME</FieldLabel>
            <Input
              size="sm"
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Box>
          <Box>
            <FieldLabel>DAG BUNDLE</FieldLabel>
            <select
              value={edit.bundle}
              style={selectStyle}
              onChange={(e) => setEdit({ ...edit, bundle: e.target.value })}
            >
              {bundles.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
            </select>
          </Box>
          <Box>
            <FieldLabel>DIRECTORY PREFIX (team's folder in the bundle)</FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              value={edit.path_prefix}
              onChange={(e) => setEdit({ ...edit, path_prefix: e.target.value })}
              placeholder="e.g. teams/data — empty = whole bundle"
            />
          </Box>
          <Box>
            <FieldLabel>GIT BRANCH (push target)</FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              value={edit.git_branch}
              onChange={(e) => setEdit({ ...edit, git_branch: e.target.value })}
              placeholder="main"
            />
          </Box>
          <Box gridColumn="1 / span 2">
            <FieldLabel>
              GIT REPOSITORY URL (optional override — empty = bundle's own remote)
            </FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              value={edit.git_remote_url}
              onChange={(e) => setEdit({ ...edit, git_remote_url: e.target.value })}
              placeholder="git@github.com:acme/dags.git"
            />
          </Box>
        </Grid>
        <Flex align="center" gap={3} mt={2}>
          <Flex gap={1} align="center">
            <input
              id={`edit-push-${team.id}`}
              type="checkbox"
              checked={edit.git_push}
              onChange={(e) => setEdit({ ...edit, git_push: e.target.checked })}
            />
            <label
              htmlFor={`edit-push-${team.id}`}
              title="Automatically commit & push to the team repo after every deploy"
            >
              <Text fontSize="xs">push on deploy</Text>
            </label>
          </Flex>
          <Box flex="1" />
          <Button size="2xs" variant="outline" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button size="2xs" colorPalette="blue" onClick={saveEdit} disabled={!edit.name.trim()}>
            Save
          </Button>
        </Flex>
      </Box>
    );
  }

  return (
    <Box borderWidth="1px" borderRadius="md" p={3}>
      <Flex align="center" gap={2} mb={1}>
        <FiUsers />
        <Text fontWeight="bold">{team.name}</Text>
        <Badge colorPalette="purple" fontFamily="mono">
          {team.bundle}
          {team.path_prefix ? `/${team.path_prefix}` : ""}
        </Badge>
        {team.git_remote_url ? (
          <Badge
            colorPalette={team.git_push ? "green" : "gray"}
            title={`${team.git_remote_url} → ${team.git_branch}`}
          >
            <FiGitBranch />
            {team.git_remote_url.replace(/^.*[:/]([^/]+\/[^/]+?)(\.git)?$/, "$1")}:
            {team.git_branch}
            {team.git_push ? " · auto" : ""}
          </Badge>
        ) : bundleGit ? (
          <Badge colorPalette="gray">
            <FiGitBranch /> origin
          </Badge>
        ) : undefined}
        <Box flex="1" />
        <IconButton
          size="2xs"
          variant="ghost"
          aria-label="Edit team"
          onClick={() => {
            setEdit({
              name: team.name,
              bundle: team.bundle,
              path_prefix: team.path_prefix,
              git_remote_url: team.git_remote_url ?? "",
              git_branch: team.git_branch,
              git_push: team.git_push,
            });
            setEditing(true);
          }}
        >
          <FiEdit2 />
        </IconButton>
        {confirmDelete ? (
          <Flex gap={1}>
            <Button size="2xs" variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button
              size="2xs"
              colorPalette="red"
              onClick={() => void api.deleteTeam(team.id).then(onChanged)}
            >
              Confirm delete
            </Button>
          </Flex>
        ) : (
          <IconButton
            size="2xs"
            variant="ghost"
            colorPalette="red"
            aria-label="Delete team"
            onClick={() => setConfirmDelete(true)}
          >
            <FiTrash2 />
          </IconButton>
        )}
      </Flex>
      {team.description ? (
        <Text fontSize="xs" color="fg.muted" mb={2}>
          {team.description}
        </Text>
      ) : undefined}
      <Flex gap={1} wrap="wrap" align="center">
        {team.members.map((member) => (
          <Badge key={member} colorPalette="blue" gap={1}>
            {member}
            <Box
              as="button"
              cursor="pointer"
              onClick={() => void api.removeTeamMember(team.id, member).then(onChanged)}
              title="Remove from team"
            >
              ✕
            </Box>
          </Badge>
        ))}
        <Input
          size="2xs"
          w="140px"
          placeholder="add username…"
          value={newMember}
          onChange={(event) => setNewMember(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              addMember();
            }
          }}
        />
        <IconButton size="2xs" variant="subtle" aria-label="Add member" onClick={addMember}>
          <FiPlus />
        </IconButton>
      </Flex>
    </Box>
  );
};

export const TeamsAdmin: FC<{ onClose: () => void }> = ({ onClose }) => {
  const bundles = useStore((s) => s.bundles);
  const [teams, setTeams] = useState<TeamInfo[] | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [name, setName] = useState("");
  const [bundle, setBundle] = useState(bundles[0]?.name ?? "");
  const [prefix, setPrefix] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [gitPush, setGitPush] = useState(false);

  const reload = () => {
    api
      .teams()
      .then(setTeams)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  };

  useEffect(reload, []);

  const create = () => {
    if (!name.trim() || !bundle) {
      return;
    }
    void api
      .createTeam({
        name: name.trim(),
        description: null,
        bundle,
        path_prefix: prefix.trim().replace(/^\/+|\/+$/g, ""),
        git_remote_url: repoUrl.trim() || null,
        git_branch: branch.trim() || "main",
        git_push: gitPush,
      })
      .then(() => {
        setName("");
        setPrefix("");
        setRepoUrl("");
        setBranch("main");
        reload();
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  };

  return (
    <Modal title="Teams" wide>
      {error ? (
        <Text fontSize="sm" color="red.solid" mb={2}>
          {error}
        </Text>
      ) : undefined}

      <Box borderWidth="1px" borderRadius="md" p={3} mb={4} bg="bg.muted">
        <Text fontSize="xs" fontWeight="bold" color="fg.muted" mb={2}>
          NEW TEAM
        </Text>
        <Grid templateColumns="1.2fr 1fr 1fr" gap={2}>
          <Box>
            <FieldLabel>TEAM NAME</FieldLabel>
            <Input
              size="sm"
              placeholder="data-team"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Box>
          <Box>
            <FieldLabel>DAG BUNDLE</FieldLabel>
            <select value={bundle} style={selectStyle} onChange={(e) => setBundle(e.target.value)}>
              {bundles.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name}
                </option>
              ))}
            </select>
          </Box>
          <Box>
            <FieldLabel>DIRECTORY PREFIX</FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              placeholder="teams/data — empty = whole bundle"
              value={prefix}
              onChange={(event) => setPrefix(event.target.value)}
            />
          </Box>
        </Grid>
        <Grid templateColumns="2fr 1fr auto auto" gap={2} mt={2} alignItems="end">
          <Box>
            <FieldLabel>GIT REPOSITORY URL (optional — empty = bundle's remote)</FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              placeholder="git@github.com:acme/dags.git"
              value={repoUrl}
              onChange={(event) => setRepoUrl(event.target.value)}
            />
          </Box>
          <Box>
            <FieldLabel>GIT BRANCH</FieldLabel>
            <Input
              size="sm"
              fontFamily="mono"
              placeholder="main"
              value={branch}
              onChange={(event) => setBranch(event.target.value)}
            />
          </Box>
          <Flex gap={1} align="center" whiteSpace="nowrap" pb={1.5}>
            <input
              id="team-git-push"
              type="checkbox"
              checked={gitPush}
              onChange={(event) => setGitPush(event.target.checked)}
            />
            <label htmlFor="team-git-push" title="Automatically commit & push to the team repo after every deploy">
              <Text fontSize="xs">push on deploy</Text>
            </label>
          </Flex>
          <Button size="sm" onClick={create} disabled={!name.trim() || !bundle}>
            <FiPlus /> Create
          </Button>
        </Grid>
        <Text fontSize="2xs" color="fg.muted" mt={2}>
          A team owns every file under its bundle + prefix: only members (and admins) can
          edit them. New DAGs created by members land in the team directory and get a{" "}
          <b>team:&lt;name&gt;</b> tag — filter the Airflow DAG list by that tag. "Commit
          &amp; push" (and, when enabled, every deploy) pushes to the team repo/branch.
        </Text>
      </Box>

      {teams === undefined && !error ? <Spinner /> : undefined}
      <Stack gap={2} maxH="50vh" overflowY="auto">
        {(teams ?? []).map((team) => (
          <TeamCard key={team.id} team={team} bundles={bundles} onChanged={reload} />
        ))}
        {teams !== undefined && teams.length === 0 ? (
          <Text fontSize="sm" color="fg.muted">
            No teams yet — create the first one above.
          </Text>
        ) : undefined}
      </Stack>

      <Flex justify="flex-end" mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      </Flex>
    </Modal>
  );
};
