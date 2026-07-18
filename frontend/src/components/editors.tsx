import { Box, Button, Flex, IconButton, Input, Stack, Text } from "@chakra-ui/react";
import { python } from "@codemirror/lang-python";
import CodeMirror from "@uiw/react-codemirror";
import type { FC } from "react";
import { useRef, useState } from "react";
import {
  FiBold,
  FiCode,
  FiItalic,
  FiLink,
  FiList,
  FiMinus,
  FiPlus,
  FiTrash2,
  FiType,
  FiUnderline,
} from "react-icons/fi";

import { parseDictLiteral, toDictLiteral } from "src/lib/dict";
import { Modal } from "src/components/Modal";

// --- Code editor modal (ported from the original app's CodeEditorModal) -----

export const CodeEditorModal: FC<{
  title: string;
  value: string;
  description?: string | null;
  onSave: (value: string) => void;
  onClose: () => void;
}> = ({ title, value, description, onSave, onClose }) => {
  const [draft, setDraft] = useState(value);

  return (
    <Modal title={title} wide>
      {description ? (
        <Text fontSize="xs" color="fg.muted" mb={2}>
          {description}
        </Text>
      ) : undefined}
      <Box borderWidth="1px" borderRadius="md" overflow="hidden">
        <CodeMirror
          value={draft}
          onChange={setDraft}
          theme="dark"
          extensions={[python()]}
          height="50vh"
          autoFocus
          style={{ fontSize: "13px" }}
        />
      </Box>
      <Flex justify="flex-end" gap={2} mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          colorPalette="blue"
          onClick={() => {
            onSave(draft);
            onClose();
          }}
        >
          Save
        </Button>
      </Flex>
    </Modal>
  );
};

// --- WYSIWYG editor modal for HTML params (ported from WysiwygEditorModal) --

export const HtmlEditorModal: FC<{
  title: string;
  value: string;
  onSave: (value: string) => void;
  onClose: () => void;
}> = ({ title, value, onSave, onClose }) => {
  const editorRef = useRef<HTMLDivElement | null>(null);
  const [sourceMode, setSourceMode] = useState(false);
  const [source, setSource] = useState(value);

  const currentHtml = (): string =>
    sourceMode ? source : (editorRef.current?.innerHTML ?? source);

  const exec = (command: string, arg?: string) => {
    editorRef.current?.focus();
    document.execCommand(command, false, arg);
  };

  const toolbar: { icon: FC; title: string; action: () => void }[] = [
    { icon: FiBold, title: "Bold", action: () => exec("bold") },
    { icon: FiItalic, title: "Italic", action: () => exec("italic") },
    { icon: FiUnderline, title: "Underline", action: () => exec("underline") },
    { icon: FiType, title: "Heading", action: () => exec("formatBlock", "<h3>") },
    { icon: FiList, title: "Bullet list", action: () => exec("insertUnorderedList") },
    { icon: FiMinus, title: "Horizontal rule", action: () => exec("insertHorizontalRule") },
    {
      icon: FiLink,
      title: "Link",
      action: () => {
        const url = window.prompt("Link URL:");
        if (url) {
          exec("createLink", url);
        }
      },
    },
  ];

  const switchMode = () => {
    if (sourceMode) {
      setSourceMode(false); // editor div re-renders from `source`
    } else {
      setSource(editorRef.current?.innerHTML ?? source);
      setSourceMode(true);
    }
  };

  return (
    <Modal title={title} wide>
      <Flex align="center" gap={1} mb={2} wrap="wrap">
        {toolbar.map((item) => (
          <IconButton
            key={item.title}
            size="xs"
            variant="subtle"
            aria-label={item.title}
            title={item.title}
            disabled={sourceMode}
            onClick={item.action}
          >
            <item.icon />
          </IconButton>
        ))}
        <Box flex="1" />
        <Button size="xs" variant={sourceMode ? "solid" : "outline"} onClick={switchMode}>
          <FiCode /> HTML source
        </Button>
      </Flex>
      {sourceMode ? (
        <Box borderWidth="1px" borderRadius="md" overflow="hidden">
          <CodeMirror
            value={source}
            onChange={setSource}
            theme="dark"
            height="45vh"
            style={{ fontSize: "13px" }}
          />
        </Box>
      ) : (
        <Box
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          dangerouslySetInnerHTML={{ __html: source }}
          borderWidth="1px"
          borderRadius="md"
          minH="45vh"
          maxH="55vh"
          overflowY="auto"
          p={4}
          fontSize="sm"
          css={{
            outline: "none",
            "& h1, & h2, & h3": { fontWeight: "bold", margin: "0.5em 0" },
            "& ul, & ol": { paddingLeft: "1.5em", margin: "0.5em 0" },
            "& a": { color: "var(--chakra-colors-blue-solid)", textDecoration: "underline" },
            "& hr": { margin: "0.75em 0" },
          }}
        />
      )}
      <Flex justify="flex-end" gap={2} mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          colorPalette="blue"
          onClick={() => {
            onSave(currentHtml());
            onClose();
          }}
        >
          Save
        </Button>
      </Flex>
    </Modal>
  );
};

// --- Key/value editor modal (ported from KeyValueEditorModal) ---------------

type Pair = { id: number; key: string; value: string };

export const KeyValueModal: FC<{
  title: string;
  value: string;
  onSave: (value: string) => void;
  onClose: () => void;
}> = ({ title, value, onSave, onClose }) => {
  const parsed = parseDictLiteral(value);
  const [pairs, setPairs] = useState<Pair[]>(
    (parsed ?? []).map(([key, val], index) => ({ id: index, key, value: val })),
  );
  const [nextId, setNextId] = useState((parsed ?? []).length);
  const unparseable = parsed === null && value.trim() !== "";

  const update = (id: number, patch: Partial<Pair>) => {
    setPairs((current) => current.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  };

  return (
    <Modal title={title}>
      {unparseable ? (
        <Text fontSize="xs" color="orange.solid" mb={2}>
          The current value is not a simple dict literal — saving here will replace it.
        </Text>
      ) : undefined}
      <Stack gap={2}>
        <Flex gap={2} px={1}>
          <Text fontSize="2xs" fontWeight="bold" color="fg.muted" flex="1">
            KEY
          </Text>
          <Text fontSize="2xs" fontWeight="bold" color="fg.muted" flex="1">
            VALUE
          </Text>
          <Box w="32px" />
        </Flex>
        {pairs.map((pair) => (
          <Flex key={pair.id} gap={2} align="center">
            <Input
              size="sm"
              fontFamily="mono"
              placeholder="key"
              value={pair.key}
              onChange={(event) => update(pair.id, { key: event.target.value })}
            />
            <Input
              size="sm"
              fontFamily="mono"
              placeholder="value"
              value={pair.value}
              onChange={(event) => update(pair.id, { value: event.target.value })}
            />
            <IconButton
              size="sm"
              variant="ghost"
              colorPalette="red"
              aria-label="Remove"
              onClick={() => setPairs((current) => current.filter((p) => p.id !== pair.id))}
            >
              <FiTrash2 />
            </IconButton>
          </Flex>
        ))}
        <Button
          size="sm"
          variant="outline"
          alignSelf="flex-start"
          onClick={() => {
            setPairs((current) => [...current, { id: nextId, key: "", value: "" }]);
            setNextId((id) => id + 1);
          }}
        >
          <FiPlus /> Add row
        </Button>
      </Stack>
      <Flex justify="flex-end" gap={2} mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          colorPalette="blue"
          onClick={() => {
            onSave(
              toDictLiteral(
                pairs.filter((p) => p.key.trim() !== "").map((p) => [p.key.trim(), p.value]),
              ),
            );
            onClose();
          }}
        >
          Save
        </Button>
      </Flex>
    </Modal>
  );
};
