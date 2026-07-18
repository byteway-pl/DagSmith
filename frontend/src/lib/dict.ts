// Pure helpers for the key:value parameter editor — no React deps, unit-tested.

/** Tolerant parse of a flat Python/JSON dict literal into pairs; null if not parseable. */
export const parseDictLiteral = (source: string): [string, string][] | null => {
  const text = source.trim();
  if (!text.startsWith("{") || !text.endsWith("}")) {
    return null;
  }
  const inner = text.slice(1, -1).trim();
  if (inner === "") {
    return [];
  }
  // Split on top-level commas (flat dicts only — nested braces bail out).
  let depth = 0;
  let current = "";
  const parts: string[] = [];
  for (const char of inner) {
    if ("{[(".includes(char)) {
      depth += 1;
    }
    if ("}])".includes(char)) {
      depth -= 1;
    }
    if (char === "," && depth === 0) {
      parts.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  if (current.trim()) {
    parts.push(current);
  }
  const pairs: [string, string][] = [];
  for (const part of parts) {
    const colon = part.indexOf(":");
    if (colon < 0) {
      return null;
    }
    const rawKey = part.slice(0, colon).trim();
    const rawValue = part.slice(colon + 1).trim();
    const keyMatch = rawKey.match(/^['"](.*)['"]$/);
    if (!keyMatch) {
      return null;
    }
    const valueMatch = rawValue.match(/^['"](.*)['"]$/);
    pairs.push([keyMatch[1], valueMatch ? valueMatch[1] : rawValue]);
  }
  return pairs;
};

const isBareValue = (value: string): boolean =>
  /^-?\d+(\.\d+)?$/.test(value) ||
  ["True", "False", "None"].includes(value) ||
  /^\{.*\}$|^\[.*\]$/.test(value);

/** Serialize pairs back to a Python dict literal. */
export const toDictLiteral = (pairs: [string, string][]): string => {
  if (pairs.length === 0) {
    return "{}";
  }
  const body = pairs
    .map(([key, value]) => {
      const rendered = isBareValue(value.trim())
        ? value.trim()
        : `'${value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
      return `'${key.replace(/'/g, "\\'")}': ${rendered}`;
    })
    .join(", ");
  return `{${body}}`;
};
