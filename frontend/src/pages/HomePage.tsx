import { Badge, Box, Button, Flex, Heading, Spinner, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useEffect, useState } from "react";

import type { PluginProps } from "src/types";
import { AuditPanel } from "src/components/AuditPanel";
import { EditorView } from "src/components/EditorView";
import { FileBrowser } from "src/components/FileBrowser";
import { TeamsAdmin } from "src/components/TeamsAdmin";
import { startAutosave, useStore } from "src/state/store";

export const HomePage: FC<PluginProps> = () => {
  const loading = useStore((s) => s.loading);
  const config = useStore((s) => s.config);
  const draft = useStore((s) => s.draft);
  const source = useStore((s) => s.source);
  const notice = useStore((s) => s.notice);
  const setNotice = useStore((s) => s.setNotice);
  const [showAudit, setShowAudit] = useState(false);
  const [showTeams, setShowTeams] = useState(false);

  useEffect(() => {
    void useStore.getState().init();
    startAutosave();
  }, []);

  useEffect(() => {
    if (notice && notice.type !== "error") {
      const timer = window.setTimeout(() => setNotice(undefined), 4000);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [notice, setNotice]);

  const fileOpen = draft !== undefined || source !== "";

  if (loading) {
    return (
      <Flex p={10} justify="center">
        <Spinner />
      </Flex>
    );
  }

  return (
    <Flex direction="column" p={4} gap={3} h="calc(100vh - 60px)" minH="480px">
      <Flex align="center" gap={3}>
        <Heading size="lg">DagSmith</Heading>
        {config ? (
          <Badge colorPalette={config.can_deploy ? "green" : "orange"}>
            {config.can_deploy
              ? "deploy enabled"
              : config.can_edit
                ? "drafts only (deploy disabled)"
                : "read-only"}
          </Badge>
        ) : undefined}
        <Box flex="1" />
        {config?.is_admin ? (
          <Button size="xs" variant="outline" onClick={() => setShowTeams(true)}>
            Teams
          </Button>
        ) : undefined}
        {config?.can_edit ? (
          <Button size="xs" variant="outline" onClick={() => setShowAudit(true)}>
            Audit
          </Button>
        ) : undefined}
        {config?.username ? (
          <Text fontSize="sm" color="fg.muted">
            {config.username}
          </Text>
        ) : undefined}
      </Flex>

      {showAudit ? <AuditPanel onClose={() => setShowAudit(false)} /> : undefined}
      {showTeams ? <TeamsAdmin onClose={() => setShowTeams(false)} /> : undefined}

      {notice ? (
        <Flex
          align="center"
          gap={2}
          p={2}
          borderRadius="md"
          bg={
            notice.type === "error"
              ? "red.subtle"
              : notice.type === "success"
                ? "green.subtle"
                : "bg.muted"
          }
        >
          <Text fontSize="sm" flex="1">
            {notice.text}
          </Text>
          <Button size="2xs" variant="ghost" onClick={() => setNotice(undefined)}>
            ✕
          </Button>
        </Flex>
      ) : undefined}

      <Box flex="1" minH="0">
        {fileOpen ? <EditorView /> : <FileBrowser />}
      </Box>
    </Flex>
  );
};
