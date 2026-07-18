import { Box, Flex, Icon, Input, Stack, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useMemo, useState } from "react";
import { FiChevronDown, FiChevronRight } from "react-icons/fi";

import type { BlockDef } from "src/api/types";
import { blockIcon, categoryIcon } from "src/components/blockIcons";
import { useStore } from "src/state/store";

export const DRAG_MIME = "application/x-dagsmith-block";

const PaletteItem: FC<{ block: BlockDef; onAdd: (block: BlockDef) => void }> = ({
  block,
  onAdd,
}) => {
  const { Icon: ItemIcon, color } = blockIcon(
    block.block_id,
    block.label,
    block.category,
    false,
  );
  return (
    <Flex
      align="center"
      gap={2}
      borderWidth="1px"
      borderRadius="md"
      px={2}
      py={1.5}
      cursor="grab"
      _active={{ cursor: "grabbing" }}
      _hover={{ bg: "bg.muted", borderColor: "blue.solid" }}
      onClick={() => onAdd(block)}
      title={block.description}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData(DRAG_MIME, block.block_id);
        event.dataTransfer.effectAllowed = "move";
      }}
    >
      <Icon as={ItemIcon} boxSize={4} color={color} flexShrink={0} />
      <Box minW={0}>
        <Text fontSize="sm" fontWeight="medium" truncate>
          {block.label}
        </Text>
      </Box>
    </Flex>
  );
};

export const Palette: FC = () => {
  const blocks = useStore((s) => s.blocks);
  const { addBlock } = useStore.getState();
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const searching = query.trim().length > 0;

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return blocks;
    }
    return blocks.filter(
      (block) =>
        block.label.toLowerCase().includes(needle) ||
        block.category.toLowerCase().includes(needle) ||
        block.description.toLowerCase().includes(needle),
    );
  }, [blocks, query]);

  const byCategory = useMemo(() => {
    const groups = new Map<string, BlockDef[]>();
    for (const block of filtered) {
      const list = groups.get(block.category) ?? [];
      list.push(block);
      groups.set(block.category, list);
    }
    return [...groups.entries()].sort(([a], [b]) =>
      a === "Core" ? -1 : b === "Core" ? 1 : a.localeCompare(b),
    );
  }, [filtered]);

  const toggle = (category: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  return (
    <Stack gap={2} p={2} h="100%" minH="0">
      <Text fontWeight="bold" fontSize="sm">
        Blocks
      </Text>
      <Input
        size="sm"
        placeholder="Search operators…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <Box overflowY="auto" flex="1" minH="0">
        <Stack gap={1}>
          {byCategory.map(([category, items]) => {
            const { Icon: CatIcon, color } = categoryIcon(category);
            // While searching every matching category is expanded.
            const isOpen = searching || expanded.has(category);
            return (
              <Box key={category}>
                <Flex
                  align="center"
                  gap={2}
                  px={1}
                  py={1.5}
                  cursor="pointer"
                  borderRadius="md"
                  _hover={{ bg: "bg.muted" }}
                  onClick={() => toggle(category)}
                >
                  <Icon
                    as={isOpen ? FiChevronDown : FiChevronRight}
                    boxSize={3.5}
                    color="fg.muted"
                  />
                  <Icon as={CatIcon} boxSize={4} color={color} />
                  <Text fontSize="xs" fontWeight="bold" flex="1" truncate>
                    {category}
                  </Text>
                  <Text fontSize="2xs" color="fg.muted">
                    {items.length}
                  </Text>
                </Flex>
                {isOpen ? (
                  <Stack gap={1} pl={5} pb={1}>
                    {items.map((block) => (
                      <PaletteItem
                        key={block.block_id}
                        block={block}
                        onAdd={(b) => addBlock(b.block_id)}
                      />
                    ))}
                  </Stack>
                ) : undefined}
              </Box>
            );
          })}
          {filtered.length === 0 ? (
            <Text fontSize="xs" color="fg.muted">
              No blocks match “{query}”.
            </Text>
          ) : undefined}
        </Stack>
      </Box>
    </Stack>
  );
};
