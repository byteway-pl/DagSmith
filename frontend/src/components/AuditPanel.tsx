import { Badge, Box, Button, Flex, Spinner, Table, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useEffect, useState } from "react";

import { api } from "src/api/client";
import type { AuditEntry } from "src/api/types";
import { Modal } from "src/components/Modal";

export const AuditPanel: FC<{ onClose: () => void }> = ({ onClose }) => {
  const [entries, setEntries] = useState<AuditEntry[] | undefined>();
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    api
      .audit(200)
      .then(setEntries)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      );
  }, []);

  return (
    <Modal title="Deploy audit log" wide>
      {error ? <Text color="red.solid">{error}</Text> : undefined}
      {entries === undefined && !error ? <Spinner /> : undefined}
      {entries !== undefined ? (
        entries.length === 0 ? (
          <Text color="fg.muted">No deploys recorded yet.</Text>
        ) : (
          <Box overflowX="auto" maxH="60vh" overflowY="auto">
            <Table.Root size="sm">
              <Table.Header>
                <Table.Row>
                  <Table.ColumnHeader>Time (UTC)</Table.ColumnHeader>
                  <Table.ColumnHeader>User</Table.ColumnHeader>
                  <Table.ColumnHeader>File</Table.ColumnHeader>
                  <Table.ColumnHeader>Version</Table.ColumnHeader>
                  <Table.ColumnHeader>Git</Table.ColumnHeader>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {entries.map((entry, index) => (
                  <Table.Row key={index}>
                    <Table.Cell whiteSpace="nowrap" fontSize="xs">
                      {entry.ts.replace("T", " ").slice(0, 19)}
                    </Table.Cell>
                    <Table.Cell fontSize="xs">{entry.user ?? "—"}</Table.Cell>
                    <Table.Cell fontFamily="mono" fontSize="xs">
                      {entry.bundle}/{entry.rel_path}
                    </Table.Cell>
                    <Table.Cell fontSize="xs">v{entry.version_no}</Table.Cell>
                    <Table.Cell fontSize="xs">
                      {entry.git_error ? (
                        <Badge colorPalette="red" title={entry.git_error}>
                          error
                        </Badge>
                      ) : entry.git_commit_sha ? (
                        <Badge colorPalette={entry.git_pushed ? "green" : "blue"}>
                          {entry.git_commit_sha.slice(0, 8)}
                          {entry.git_pushed ? " ↑" : ""}
                        </Badge>
                      ) : (
                        "—"
                      )}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table.Root>
          </Box>
        )
      ) : undefined}
      <Flex justify="flex-end" mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Close
        </Button>
      </Flex>
    </Modal>
  );
};
