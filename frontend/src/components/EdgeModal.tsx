import { Button, Code, Flex, Input, Stack, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useState } from "react";

import { Modal } from "src/components/Modal";
import { useStore } from "src/state/store";

export const EdgeModal: FC<{
  source: string;
  target: string;
  onClose: () => void;
}> = ({ source, target, onClose }) => {
  const graph = useStore((s) => s.graph);
  const { mutateGraph } = useStore.getState();
  const edge = graph?.edges.find((e) => e.source === source && e.target === target);
  const [label, setLabel] = useState(edge?.label ?? "");

  if (!graph || !edge) {
    return null;
  }

  const apply = () => {
    mutateGraph((g) => ({
      ...g,
      edges: g.edges.map((e) =>
        e.source === source && e.target === target
          ? { ...e, label: label.trim() || null }
          : e,
      ),
    }));
    onClose();
  };

  const remove = () => {
    mutateGraph((g) => ({
      ...g,
      edges: g.edges.filter((e) => !(e.source === source && e.target === target)),
    }));
    onClose();
  };

  return (
    <Modal title={`Edge: ${source} → ${target}`}>
      <Stack gap={1}>
        <Text fontSize="xs" fontWeight="medium" color="fg.muted">
          Label
        </Text>
        <Input
          size="sm"
          placeholder='e.g. "on success", "retry path"'
          autoFocus
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              apply();
            }
          }}
        />
        <Text fontSize="2xs" color="fg.muted">
          Rendered in code as{" "}
          <Code fontSize="2xs">
            {source} &gt;&gt; Label(…) &gt;&gt; {target}
          </Code>
          . Run conditions (trigger_rule) live on the task — select the downstream task to
          set it.
        </Text>
      </Stack>

      <Flex justify="space-between" mt={4}>
        <Button size="sm" variant="outline" colorPalette="red" onClick={remove}>
          Delete edge
        </Button>
        <Flex gap={2}>
          <Button size="sm" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" colorPalette="blue" onClick={apply}>
            Apply
          </Button>
        </Flex>
      </Flex>
    </Modal>
  );
};
