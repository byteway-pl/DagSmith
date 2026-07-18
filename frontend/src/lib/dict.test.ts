import { describe, expect, it } from "vitest";

import { parseDictLiteral, toDictLiteral } from "./dict";

describe("parseDictLiteral", () => {
  it("parses a flat dict with string values", () => {
    expect(parseDictLiteral("{'a': 'x', 'b': 'y'}")).toEqual([
      ["a", "x"],
      ["b", "y"],
    ]);
  });

  it("keeps bare (non-string) values verbatim", () => {
    expect(parseDictLiteral("{'retries': 3, 'flag': True}")).toEqual([
      ["retries", "3"],
      ["flag", "True"],
    ]);
  });

  it("returns [] for an empty dict", () => {
    expect(parseDictLiteral("{}")).toEqual([]);
  });

  it("does not split on commas inside nested braces", () => {
    expect(parseDictLiteral("{'x': [1, 2], 'y': 'z'}")).toEqual([
      ["x", "[1, 2]"],
      ["y", "z"],
    ]);
  });

  it("returns null for non-dict / unparseable input", () => {
    expect(parseDictLiteral("not a dict")).toBeNull();
    expect(parseDictLiteral("lambda: 1")).toBeNull();
    expect(parseDictLiteral("{invalid}")).toBeNull();
  });
});

describe("toDictLiteral", () => {
  it("quotes string values and leaves bare values unquoted", () => {
    expect(
      toDictLiteral([
        ["name", "alice"],
        ["retries", "3"],
        ["flag", "False"],
      ]),
    ).toBe("{'name': 'alice', 'retries': 3, 'flag': False}");
  });

  it("returns {} for no pairs", () => {
    expect(toDictLiteral([])).toBe("{}");
  });

  it("round-trips string dicts through parse+serialize", () => {
    const src = "{'env': 'prod', 'region': 'eu'}";
    const parsed = parseDictLiteral(src);
    expect(parsed).not.toBeNull();
    expect(toDictLiteral(parsed!)).toBe(src);
  });

  it("escapes single quotes in values", () => {
    expect(toDictLiteral([["msg", "it's fine"]])).toBe("{'msg': 'it\\'s fine'}");
  });
});
