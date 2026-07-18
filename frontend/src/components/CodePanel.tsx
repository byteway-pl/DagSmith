import { python } from "@codemirror/lang-python";
import CodeMirror from "@uiw/react-codemirror";
import type { FC } from "react";
import { useMemo } from "react";

const isDarkMode = (): boolean =>
  document.documentElement.classList.contains("dark") ||
  document.documentElement.dataset.theme === "dark";

export const CodePanel: FC<{
  value: string;
  readOnly: boolean;
  onChange: (value: string) => void;
}> = ({ value, readOnly, onChange }) => {
  const dark = useMemo(isDarkMode, []);

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      theme={dark ? "dark" : "light"}
      extensions={[python()]}
      height="100%"
      style={{ height: "100%", fontSize: "13px" }}
    />
  );
};
