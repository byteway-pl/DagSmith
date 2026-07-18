import { Badge, Box, Button, Flex, Stack, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useState } from "react";

import { api } from "src/api/client";
import type { VersionDetail } from "src/api/types";
import { DiffView } from "src/components/DiffView";
import { Modal } from "src/components/Modal";
import { useStore } from "src/state/store";

const kindPalette: Record<string, string> = {
  auto: "gray",
  manual: "blue",
  deploy: "green",
};

export const HistoryPanel: FC = () => {
  const draft = useStore((s) => s.draft);
  const history = useStore((s) => s.history);
  const source = useStore((s) => s.source);
  const restore = useStore((s) => s.restore);
  const [preview, setPreview] = useState<VersionDetail | undefined>();

  if (!draft || !history) {
    return null;
  }

  return (
    <Box w="320px" borderLeftWidth="1px" overflowY="auto" p={3}>
      <Text fontWeight="bold" mb={2}>
        History
      </Text>
      <Stack gap={2}>
        {history.map((version) => (
          <Box key={version.version_no} borderWidth="1px" borderRadius="md" p={2}>
            <Flex justify="space-between" align="center">
              <Text fontWeight="medium" fontSize="sm">
                v{version.version_no}
                {version.version_no === draft.head_version_no ? " (head)" : ""}
              </Text>
              <Badge colorPalette={kindPalette[version.kind] ?? "gray"} size="sm">
                {version.deployed_at ? "deployed" : version.kind}
              </Badge>
            </Flex>
            <Text fontSize="xs" color="fg.muted">
              {new Date(version.created_at).toLocaleString()}
              {version.created_by ? ` · ${version.created_by}` : ""}
            </Text>
            {version.message ? (
              <Text fontSize="xs" mt={1}>
                {version.message}
              </Text>
            ) : undefined}
            <Flex gap={2} mt={2}>
              <Button
                size="2xs"
                variant="outline"
                onClick={() => {
                  void api
                    .version(draft.id, version.version_no)
                    .then((detail) => setPreview(detail));
                }}
              >
                Diff
              </Button>
              {version.version_no !== draft.head_version_no ? (
                <Button size="2xs" onClick={() => void restore(version.version_no)}>
                  Restore
                </Button>
              ) : undefined}
            </Flex>
          </Box>
        ))}
      </Stack>

      {preview ? (
        <Modal title={`v${preview.version_no} vs current editor`} wide>
          <DiffView left={preview.source} right={source} />
          <Flex justify="flex-end" gap={2} mt={4}>
            {preview.version_no !== draft.head_version_no ? (
              <Button
                size="sm"
                onClick={() => {
                  void restore(preview.version_no);
                  setPreview(undefined);
                }}
              >
                Restore v{preview.version_no}
              </Button>
            ) : undefined}
            <Button size="sm" variant="outline" onClick={() => setPreview(undefined)}>
              Close
            </Button>
          </Flex>
        </Modal>
      ) : undefined}
    </Box>
  );
};
