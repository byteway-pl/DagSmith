import { Box, Button, Code, Flex, Grid, Stack, Text } from "@chakra-ui/react";
import type { FC } from "react";
import { useMemo, useState } from "react";

import { Modal } from "src/components/Modal";

// Ported from the original app's CronGeneratorModal: quick presets, and per
// cron field an Every/Specific toggle with a clickable value-chip grid,
// plus a live expression preview and human-readable summary.

const PRESETS: { label: string; value: string }[] = [
  { label: "Hourly", value: "@hourly" },
  { label: "Daily", value: "@daily" },
  { label: "Weekly", value: "@weekly" },
  { label: "Monthly", value: "@monthly" },
  { label: "Every 15 min", value: "*/15 * * * *" },
  { label: "Every 6 hours", value: "0 */6 * * *" },
  { label: "Weekdays 6:00", value: "0 6 * * 1-5" },
  { label: "Sunday 3:00", value: "0 3 * * 0" },
];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAYS_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

type FieldState = { mode: "every" | "specific"; values: number[] };

type FieldSpec = {
  name: string;
  label: string;
  unit: string;
  options: number[];
  optionLabel?: (value: number) => string;
  columns: number;
};

const FIELDS: FieldSpec[] = [
  {
    name: "minute",
    label: "Minute",
    unit: "minute",
    options: Array.from({ length: 60 }, (_, i) => i),
    columns: 12,
  },
  {
    name: "hour",
    label: "Hour",
    unit: "hour",
    options: Array.from({ length: 24 }, (_, i) => i),
    columns: 12,
  },
  {
    name: "dom",
    label: "Day of month",
    unit: "day",
    options: Array.from({ length: 31 }, (_, i) => i + 1),
    columns: 11,
  },
  {
    name: "month",
    label: "Month",
    unit: "month",
    options: Array.from({ length: 12 }, (_, i) => i + 1),
    optionLabel: (value) => MONTHS[value - 1],
    columns: 6,
  },
  {
    name: "dow",
    label: "Day of week",
    unit: "weekday",
    options: Array.from({ length: 7 }, (_, i) => i),
    optionLabel: (value) => DAYS[value],
    columns: 7,
  },
];

const parseField = (raw: string): FieldState | null => {
  if (raw === "*") {
    return { mode: "every", values: [] };
  }
  if (/^\d+(,\d+)*$/.test(raw)) {
    return { mode: "specific", values: raw.split(",").map(Number) };
  }
  return null; // */n, ranges — not representable as chips
};

const fieldToCron = (state: FieldState): string =>
  state.mode === "every" || state.values.length === 0
    ? "*"
    : [...state.values].sort((a, b) => a - b).join(",");

const describe = (fields: Record<string, FieldState>): string => {
  const parts: string[] = [];
  const named = (state: FieldState, unit: string, names?: string[]) =>
    state.mode === "specific" && state.values.length > 0
      ? `${unit} ${[...state.values]
          .sort((a, b) => a - b)
          .map((v) => (names ? names[v - (names === MONTHS ? 1 : 0)] : v))
          .join(", ")}`
      : `every ${unit}`;
  parts.push(named(fields.minute, "minute"));
  parts.push(named(fields.hour, "hour"));
  if (fields.dom.mode === "specific" && fields.dom.values.length > 0) {
    parts.push(`day ${[...fields.dom.values].sort((a, b) => a - b).join(", ")}`);
  }
  if (fields.month.mode === "specific" && fields.month.values.length > 0) {
    parts.push(`in ${[...fields.month.values].sort((a, b) => a - b).map((m) => MONTHS[m - 1]).join(", ")}`);
  }
  if (fields.dow.mode === "specific" && fields.dow.values.length > 0) {
    parts.push(
      `on ${[...fields.dow.values].sort((a, b) => a - b).map((d) => DAYS_FULL[d]).join(", ")}`,
    );
  }
  return `At ${parts.join(", ")}`;
};

export const CronGeneratorModal: FC<{
  value: string;
  onSave: (cron: string) => void;
  onClose: () => void;
}> = ({ value, onSave, onClose }) => {
  const initial = useMemo(() => {
    const parts = value.trim().split(/\s+/);
    const defaults: Record<string, FieldState> = {
      minute: { mode: "specific", values: [0] },
      hour: { mode: "specific", values: [6] },
      dom: { mode: "every", values: [] },
      month: { mode: "every", values: [] },
      dow: { mode: "every", values: [] },
    };
    if (parts.length === 5) {
      const names = ["minute", "hour", "dom", "month", "dow"];
      const parsed: Record<string, FieldState> = {};
      for (let i = 0; i < 5; i += 1) {
        const state = parseField(parts[i]);
        if (state === null) {
          return defaults; // advanced expression — start from defaults
        }
        parsed[names[i]] = state;
      }
      return parsed;
    }
    return defaults;
  }, [value]);

  const [fields, setFields] = useState<Record<string, FieldState>>(initial);

  const setMode = (name: string, mode: "every" | "specific") =>
    setFields((current) => ({ ...current, [name]: { ...current[name], mode } }));

  const toggleValue = (name: string, valueToToggle: number) =>
    setFields((current) => {
      const state = current[name];
      const values = state.values.includes(valueToToggle)
        ? state.values.filter((v) => v !== valueToToggle)
        : [...state.values, valueToToggle];
      return { ...current, [name]: { mode: "specific", values } };
    });

  const cron = FIELDS.map((spec) => fieldToCron(fields[spec.name])).join(" ");

  return (
    <Modal title="Cron builder" wide>
      <Stack gap={4}>
        <Box>
          <Text fontSize="2xs" fontWeight="bold" color="fg.muted" mb={1}>
            PRESETS
          </Text>
          <Flex gap={1} wrap="wrap">
            {PRESETS.map((preset) => (
              <Button
                key={preset.value}
                size="2xs"
                variant="outline"
                onClick={() => {
                  onSave(preset.value);
                  onClose();
                }}
              >
                {preset.label}
              </Button>
            ))}
          </Flex>
        </Box>

        <Box maxH="46vh" overflowY="auto" pr={1}>
          <Stack gap={4}>
            {FIELDS.map((spec) => {
              const state = fields[spec.name];
              return (
                <Box key={spec.name}>
                  <Flex align="center" justify="space-between" mb={1.5}>
                    <Text fontSize="xs" fontWeight="bold">
                      {spec.label}
                    </Text>
                    <Flex borderWidth="1px" borderRadius="md" overflow="hidden">
                      <Button
                        size="2xs"
                        borderRadius="0"
                        variant={state.mode === "every" ? "solid" : "ghost"}
                        onClick={() => setMode(spec.name, "every")}
                      >
                        Every {spec.unit}
                      </Button>
                      <Button
                        size="2xs"
                        borderRadius="0"
                        variant={state.mode === "specific" ? "solid" : "ghost"}
                        onClick={() => setMode(spec.name, "specific")}
                      >
                        Specific
                      </Button>
                    </Flex>
                  </Flex>
                  {state.mode === "specific" ? (
                    <Grid templateColumns={`repeat(${spec.columns}, 1fr)`} gap={1}>
                      {spec.options.map((option) => {
                        const active = state.values.includes(option);
                        return (
                          <Button
                            key={option}
                            size="2xs"
                            fontSize="2xs"
                            variant={active ? "solid" : "outline"}
                            colorPalette={active ? "blue" : "gray"}
                            onClick={() => toggleValue(spec.name, option)}
                          >
                            {spec.optionLabel ? spec.optionLabel(option) : option}
                          </Button>
                        );
                      })}
                    </Grid>
                  ) : undefined}
                </Box>
              );
            })}
          </Stack>
        </Box>

        <Box p={3} borderWidth="1px" borderRadius="md" bg="bg.muted">
          <Code fontSize="md">{cron}</Code>
          <Text fontSize="xs" color="fg.muted" mt={1}>
            {describe(fields)}
          </Text>
        </Box>
      </Stack>
      <Flex justify="flex-end" gap={2} mt={4}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button
          size="sm"
          colorPalette="blue"
          onClick={() => {
            onSave(cron);
            onClose();
          }}
        >
          Use expression
        </Button>
      </Flex>
    </Modal>
  );
};
