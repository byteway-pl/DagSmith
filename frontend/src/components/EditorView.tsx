import {
  Badge,
  Box,
  Button,
  Code,
  Flex,
  HStack,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react";
import type { FC } from "react";
import { useEffect, useState } from "react";
import { FiGitBranch } from "react-icons/fi";

import { api } from "src/api/client";

import { Canvas } from "src/components/Canvas";
import { CodePanel } from "src/components/CodePanel";
import { DagSettingsModal } from "src/components/DagSettingsModal";
import { DiffView } from "src/components/DiffView";
import { HistoryPanel } from "src/components/HistoryPanel";
import { Inspector } from "src/components/Inspector";
import { Modal } from "src/components/Modal";
import { Palette } from "src/components/Palette";
import { useStore } from "src/state/store";

const SyncBadge: FC = () => {
  const draft = useStore((s) => s.draft);
  const dirty = useStore((s) => s.dirty);
  const liveFileHash = useStore((s) => s.liveFileHash);

  if (!draft) {
    return <Badge colorPalette="gray">read-only</Badge>;
  }
  if (liveFileHash !== draft.base_file_hash) {
    return <Badge colorPalette="red">conflict with live file</Badge>;
  }
  if (dirty) {
    return <Badge colorPalette="orange">unsaved changes</Badge>;
  }
  if (draft.status === "deployed" && draft.base_file_hash !== null) {
    return <Badge colorPalette="green">in sync with live</Badge>;
  }
  return <Badge colorPalette="blue">draft ahead of live</Badge>;
};

export const EditorView: FC = () => {
  const draft = useStore((s) => s.draft);
  const source = useStore((s) => s.source);
  const readOnly = useStore((s) => s.readOnly);
  const config = useStore((s) => s.config);
  const saving = useStore((s) => s.saving);
  const validating = useStore((s) => s.validating);
  const deploying = useStore((s) => s.deploying);
  const validation = useStore((s) => s.validation);
  const showHistory = useStore((s) => s.showHistory);
  const deployConflict = useStore((s) => s.deployConflict);
  const saveConflictHead = useStore((s) => s.saveConflictHead);
  const mode = useStore((s) => s.mode);
  const graph = useStore((s) => s.graph);
  const parseError = useStore((s) => s.parseError);
  const parseWarnings = useStore((s) => s.parseWarnings);
  const regenerating = useStore((s) => s.regenerating);

  const {
    closeFile,
    setSource,
    setMode,
    save,
    validate,
    deploy,
    toggleHistory,
    reloadDraft,
    loadFromBundle,
    cancelDeployConflict,
  } = useStore.getState();
  const [showDagSettings, setShowDagSettings] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [confirmNoGitDeploy, setConfirmNoGitDeploy] = useState(false);
  const [confirmReload, setConfirmReload] = useState(false);
  const liveFileHash = useStore((s) => s.liveFileHash);
  const bundles = useStore((s) => s.bundles);
  const teams = useStore((s) => s.teams);
  const bundleGit = draft ? (bundles.find((b) => b.name === draft.bundle)?.git ?? false) : false;

  // Team owning the open file (longest matching prefix in the file's bundle).
  const owningTeam = draft
    ? teams
        .filter(
          (t) =>
            t.bundle === draft.bundle &&
            (t.path_prefix === "" ||
              draft.rel_path === t.path_prefix ||
              draft.rel_path.startsWith(`${t.path_prefix}/`)),
        )
        .sort((a, b) => b.path_prefix.length - a.path_prefix.length)[0]
    : undefined;
  // Where would git go: the team's repo override, else the bundle checkout's
  // own upstream (a team without an override inherits the bundle's git).
  const hasGitTarget = Boolean(owningTeam?.git_remote_url) || bundleGit;

  const requestDeploy = () => {
    if (!hasGitTarget) {
      setConfirmNoGitDeploy(true);
    } else {
      void deploy();
    }
  };

  const gitPush = async () => {
    if (!draft) {
      return;
    }
    setPushing(true);
    try {
      const result = await api.gitPush(draft.id);
      useStore.setState({
        notice: result.error
          ? { type: "error", text: `Git: ${result.error}` }
          : result.commit_sha
            ? {
                type: "success",
                text:
                  `Committed ${result.commit_sha.slice(0, 8)}` +
                  (result.pushed ? " and pushed" : "") +
                  (result.web_url ? ` — ${result.web_url}` : ""),
              }
            : { type: "info", text: "Nothing to commit (file unchanged)" },
      });
    } catch (err) {
      useStore.setState({
        notice: { type: "error", text: err instanceof Error ? err.message : String(err) },
      });
    } finally {
      setPushing(false);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "s") {
        event.preventDefault();
        void save("manual");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  return (
    <Flex direction="column" h="100%" minH="0">
      <Flex align="center" gap={3} pb={3} wrap="wrap">
        <Button size="sm" variant="outline" onClick={closeFile}>
          ← Files
        </Button>
        <Text fontFamily="mono" fontWeight="medium">
          {draft?.rel_path ?? "(read-only view)"}
        </Text>
        <SyncBadge />
        {draft ? (
          <HStack gap={0} borderWidth="1px" borderRadius="md" overflow="hidden">
            {(["visual", "split", "code"] as const).map((option) => (
              <Button
                key={option}
                size="xs"
                variant={mode === option ? "solid" : "ghost"}
                borderRadius="0"
                disabled={option !== "code" && !graph}
                onClick={() => setMode(option)}
              >
                {option === "visual" ? "Visual" : option === "split" ? "Split" : "Code"}
              </Button>
            ))}
          </HStack>
        ) : undefined}
        {regenerating ? <Spinner size="xs" /> : undefined}
        {parseError && mode !== "code" ? (
          <Badge colorPalette="red" title={parseError}>
            canvas frozen — parse error
          </Badge>
        ) : undefined}
        <Box flex="1" />
        {draft ? (
          <HStack gap={2}>
            {graph && mode !== "code" ? (
              <Button size="sm" variant="outline" onClick={() => setShowDagSettings(true)}>
                DAG settings
              </Button>
            ) : undefined}
            <Button size="sm" onClick={() => void save("manual")} loading={saving}>
              Save
            </Button>
            <Button size="sm" variant="outline" onClick={() => void validate()} loading={validating}>
              Validate
            </Button>
            <Button size="sm" variant="outline" onClick={() => void toggleHistory()}>
              History
            </Button>
            {liveFileHash !== null ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmReload(true)}
                title="Discard draft edits and load the file as it is on disk (deployed)"
              >
                Load from bundle
              </Button>
            ) : undefined}
            <Button
              size="sm"
              colorPalette="green"
              onClick={requestDeploy}
              loading={deploying}
              disabled={!config?.can_deploy}
              title={config?.can_deploy ? "Validate and write the .py file" : "Deploy disabled"}
            >
              Deploy
            </Button>
            {hasGitTarget && config?.can_deploy ? (
              <Button
                size="sm"
                variant="outline"
                colorPalette="green"
                onClick={() => void gitPush()}
                loading={pushing}
                title={
                  owningTeam?.git_remote_url
                    ? `Commit and push to ${owningTeam.git_remote_url} (${owningTeam.git_branch})`
                    : "Commit and push to the bundle repo's upstream"
                }
              >
                <FiGitBranch /> Commit & push
              </Button>
            ) : undefined}
          </HStack>
        ) : undefined}
      </Flex>

      {parseWarnings.length > 0 && mode !== "code" ? (
        <Box mb={2} p={2} borderRadius="md" bg="orange.subtle">
          {parseWarnings.map((warning, index) => (
            <Text key={index} fontSize="xs">
              ⚠ {warning}
            </Text>
          ))}
        </Box>
      ) : undefined}

      <Flex flex="1" minH="0" borderWidth="1px" borderRadius="md" overflow="hidden">
        {mode === "visual" && graph && draft ? (
          <>
            <Box w="220px" minW="180px" borderRightWidth="1px">
              <Palette />
            </Box>
            <Box flex="1" minW="0">
              <Canvas />
            </Box>
            <Box w="300px" minW="260px" borderLeftWidth="1px">
              <Inspector />
            </Box>
          </>
        ) : mode === "split" && graph && draft ? (
          <>
            <Box flex="1" minW="0" borderRightWidth="1px">
              <Canvas />
            </Box>
            <Box flex="1" minW="0" overflow="auto">
              <CodePanel value={source} readOnly={readOnly} onChange={setSource} />
            </Box>
          </>
        ) : (
          <Box flex="1" minW="0" overflow="auto">
            <CodePanel value={source} readOnly={readOnly} onChange={setSource} />
          </Box>
        )}
        {showHistory ? <HistoryPanel /> : undefined}
      </Flex>

      {validation ? (
        <Box
          mt={2}
          p={2}
          borderWidth="1px"
          borderRadius="md"
          borderColor={validation.ok ? "green.solid" : "red.solid"}
          maxH="150px"
          overflowY="auto"
        >
          {validation.ok ? (
            <Text fontSize="sm">
              ✓ Valid{validation.dag_count !== null ? ` — ${validation.dag_count} DAG(s) found` : ""}
            </Text>
          ) : (
            <Stack gap={1}>
              {validation.errors.map((issue, index) => (
                <Text key={index} fontSize="sm" fontFamily="mono">
                  [{issue.kind}]{issue.line !== null ? ` line ${issue.line}:` : ""} {issue.message}
                </Text>
              ))}
            </Stack>
          )}
        </Box>
      ) : undefined}

      {deploying ? (
        <HStack mt={2}>
          <Spinner size="xs" />
          <Text fontSize="sm" color="fg.muted">
            Validating and deploying…
          </Text>
        </HStack>
      ) : undefined}

      {showDagSettings ? <DagSettingsModal onClose={() => setShowDagSettings(false)} /> : undefined}

      {confirmReload ? (
        <Modal title="Load from bundle — are you sure?">
          <Text fontSize="sm" mb={2}>
            This loads <Code>{draft?.rel_path}</Code> exactly as it is on disk right now (the
            deployed / production version) and makes it the current draft. Your unsaved and
            un-deployed draft edits will be replaced. Version history is kept — this is
            appended as a new version, so you can still restore what you had.
          </Text>
          <Flex justify="flex-end" gap={2} mt={4}>
            <Button size="sm" variant="outline" onClick={() => setConfirmReload(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              colorPalette="blue"
              onClick={() => {
                setConfirmReload(false);
                void loadFromBundle();
              }}
            >
              Load deployed version
            </Button>
          </Flex>
        </Modal>
      ) : undefined}

      {confirmNoGitDeploy ? (
        <Modal title="Deploy without git — are you sure?">
          <Text fontSize="sm" mb={2}>
            This bundle is not a git repository
            {owningTeam ? ` and team ${owningTeam.name} has no repo configured` : ""}, so
            this deploy won't be committed anywhere. Deploying will{" "}
            <b>overwrite the live file</b>. A local backup is kept, but there will be no
            history in any repository.
          </Text>
          <Flex justify="flex-end" gap={2} mt={4}>
            <Button size="sm" variant="outline" onClick={() => setConfirmNoGitDeploy(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              colorPalette="orange"
              onClick={() => {
                setConfirmNoGitDeploy(false);
                void deploy();
              }}
            >
              Deploy anyway
            </Button>
          </Flex>
        </Modal>
      ) : undefined}

      {saveConflictHead !== undefined ? (
        <Modal title="Draft changed by someone else">
          <Text mb={4}>
            The draft head is now <Code>v{saveConflictHead}</Code>, but your editor is based on
            an older version. Reload the latest version (your local changes will be lost) or
            copy your changes elsewhere first.
          </Text>
          <Flex justify="flex-end" gap={2}>
            <Button size="sm" onClick={() => void reloadDraft()}>
              Load latest version
            </Button>
          </Flex>
        </Modal>
      ) : undefined}

      {deployConflict ? (
        <Modal title="Live file changed outside DagSmith" wide>
          <Text mb={3} fontSize="sm">
            Left: current file on disk · Right: your draft. Deploying will overwrite the
            file on disk (a backup is taken first).
          </Text>
          <DiffView left={deployConflict.live_content ?? ""} right={source} />
          <Flex justify="flex-end" gap={2} mt={4}>
            <Button size="sm" variant="outline" onClick={cancelDeployConflict}>
              Cancel
            </Button>
            <Button
              size="sm"
              colorPalette="red"
              onClick={() => void deploy(deployConflict.live_file_hash)}
            >
              Overwrite live file
            </Button>
          </Flex>
        </Modal>
      ) : undefined}
    </Flex>
  );
};
