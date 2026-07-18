import { python } from "@codemirror/lang-python";
import { MergeView } from "@codemirror/merge";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { Box } from "@chakra-ui/react";
import type { FC } from "react";
import { useEffect, useRef } from "react";

// Side-by-side read-only diff (left: live file, right: draft).
export const DiffView: FC<{ left: string; right: string }> = ({ left, right }) => {
  const container = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!container.current) {
      return undefined;
    }
    const shared = [
      python(),
      EditorView.editable.of(false),
      EditorState.readOnly.of(true),
    ];
    const view = new MergeView({
      a: { doc: left, extensions: shared },
      b: { doc: right, extensions: shared },
      parent: container.current,
    });
    return () => view.destroy();
  }, [left, right]);

  return (
    <Box
      ref={container}
      borderWidth="1px"
      borderRadius="sm"
      maxH="55vh"
      overflowY="auto"
      fontSize="13px"
    />
  );
};
