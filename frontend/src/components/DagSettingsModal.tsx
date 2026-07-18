import {
  Box,
  Button,
  Flex,
  Grid,
  HStack,
  Input,
  Stack,
  Text,
  Textarea,
} from "@chakra-ui/react";
import type { FC, ReactNode } from "react";
import { useState } from "react";
import { FiCalendar, FiClock, FiMail, FiTag, FiUser } from "react-icons/fi";

import { CronGeneratorModal } from "src/components/CronGeneratorModal";
import { Modal } from "src/components/Modal";
import { useStore } from "src/state/store";

const IDENT_RE = /^[A-Za-z_][\w.\-]*$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const SCHEDULE_PRESETS = ["@once", "@hourly", "@daily", "@weekly", "@monthly", "@yearly"];

const Section: FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
  <Stack gap={2}>
    <Text fontSize="2xs" fontWeight="bold" color="fg.muted" letterSpacing="wider">
      {title.toUpperCase()}
    </Text>
    {children}
  </Stack>
);

const FieldLabel: FC<{ children: ReactNode }> = ({ children }) => (
  <Text fontSize="xs" fontWeight="medium" color="fg.muted" mb={1}>
    {children}
  </Text>
);

export const DagSettingsModal: FC<{ onClose: () => void }> = ({ onClose }) => {
  const graph = useStore((s) => s.graph);
  const { mutateGraph } = useStore.getState();
  const meta = graph?.dag;

  const [dagId, setDagId] = useState(meta?.dag_id ?? "");
  const [schedule, setSchedule] = useState(meta?.schedule ?? "");
  const [description, setDescription] = useState(meta?.description ?? "");
  const [tags, setTags] = useState((meta?.tags ?? []).join(", "));
  const [startDate, setStartDate] = useState(meta?.start_date ?? "");
  const [catchup, setCatchup] = useState<boolean>(meta?.catchup ?? false);
  const [maxActiveRuns, setMaxActiveRuns] = useState(
    meta?.max_active_runs === null || meta?.max_active_runs === undefined
      ? ""
      : String(meta.max_active_runs),
  );
  const [owner, setOwner] = useState(meta?.owner ?? "");
  const [email, setEmail] = useState(meta?.email ?? "");
  const [retries, setRetries] = useState(
    meta?.retries === null || meta?.retries === undefined ? "" : String(meta.retries),
  );
  const [retryDelay, setRetryDelay] = useState(
    meta?.retry_delay_s === null || meta?.retry_delay_s === undefined
      ? ""
      : String(meta.retry_delay_s),
  );
  const [showCron, setShowCron] = useState(false);

  if (!graph || !meta) {
    return null;
  }

  const dagIdValid = IDENT_RE.test(dagId.trim());
  const dateValid = startDate.trim() === "" || DATE_RE.test(startDate.trim());

  const save = () => {
    mutateGraph((g) => ({
      ...g,
      dag: {
        ...g.dag,
        dag_id: dagId.trim(),
        schedule: schedule.trim() || null,
        description: description.trim() || null,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
        start_date: startDate.trim() || null,
        catchup: startDate.trim() || g.dag.catchup !== null ? catchup : null,
        max_active_runs: maxActiveRuns.trim() === "" ? null : Number(maxActiveRuns),
        owner: owner.trim() || null,
        email: email.trim() || null,
        retries: retries.trim() === "" ? null : Number(retries),
        retry_delay_s: retryDelay.trim() === "" ? null : Number(retryDelay),
      },
    }));
    onClose();
  };

  return (
    <Modal title="DAG settings" wide>
      <Grid templateColumns={{ base: "1fr", md: "1fr 1fr" }} gap={6}>
        <Stack gap={4}>
          <Section title="General">
            <Box>
              <FieldLabel>DAG ID *</FieldLabel>
              <Input
                size="sm"
                fontFamily="mono"
                value={dagId}
                borderColor={dagIdValid ? undefined : "red.solid"}
                onChange={(event) => setDagId(event.target.value)}
              />
            </Box>
            <Box>
              <FieldLabel>Description</FieldLabel>
              <Textarea
                size="sm"
                rows={2}
                placeholder="This DAG processes daily data…"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Box>
            <Box>
              <FieldLabel>
                <HStack gap={1}>
                  <FiTag size={12} /> <span>Tags (comma-separated)</span>
                </HStack>
              </FieldLabel>
              <Input
                size="sm"
                placeholder="etl, sales, production"
                value={tags}
                onChange={(event) => setTags(event.target.value)}
              />
            </Box>
          </Section>

          <Section title="Schedule">
            <HStack>
              <Input
                size="sm"
                fontFamily="mono"
                placeholder="none (manual only)"
                value={schedule}
                onChange={(event) => setSchedule(event.target.value)}
              />
              <Button size="sm" variant="outline" onClick={() => setShowCron(true)}>
                <FiClock /> Cron builder
              </Button>
            </HStack>
            <Flex gap={1} wrap="wrap">
              {SCHEDULE_PRESETS.map((preset) => (
                <Button
                  key={preset}
                  size="2xs"
                  variant={schedule === preset ? "solid" : "ghost"}
                  onClick={() => setSchedule(preset)}
                >
                  {preset}
                </Button>
              ))}
              <Button
                size="2xs"
                variant={schedule === "" ? "solid" : "ghost"}
                onClick={() => setSchedule("")}
              >
                none
              </Button>
            </Flex>
          </Section>
        </Stack>

        <Stack gap={4}>
          <Section title="Timing">
            <Box>
              <FieldLabel>
                <HStack gap={1}>
                  <FiCalendar size={12} /> <span>Start date (YYYY-MM-DD)</span>
                </HStack>
              </FieldLabel>
              <Input
                size="sm"
                type="date"
                value={startDate}
                borderColor={dateValid ? undefined : "red.solid"}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </Box>
            <HStack gap={2}>
              <input
                id="dagsmith-catchup"
                type="checkbox"
                checked={catchup}
                onChange={(event) => setCatchup(event.target.checked)}
              />
              <label htmlFor="dagsmith-catchup">
                <Text fontSize="sm">Catchup (backfill past runs)</Text>
              </label>
            </HStack>
            <Box>
              <FieldLabel>Max active runs</FieldLabel>
              <Input
                size="sm"
                type="number"
                min={1}
                placeholder="unlimited"
                value={maxActiveRuns}
                onChange={(event) => setMaxActiveRuns(event.target.value)}
              />
            </Box>
          </Section>

          <Section title="Default args (all tasks)">
            <Grid templateColumns="1fr 1fr" gap={2}>
              <Box>
                <FieldLabel>
                  <HStack gap={1}>
                    <FiUser size={12} /> <span>Owner</span>
                  </HStack>
                </FieldLabel>
                <Input
                  size="sm"
                  placeholder="airflow"
                  value={owner}
                  onChange={(event) => setOwner(event.target.value)}
                />
              </Box>
              <Box>
                <FieldLabel>
                  <HStack gap={1}>
                    <FiMail size={12} /> <span>Email on failure</span>
                  </HStack>
                </FieldLabel>
                <Input
                  size="sm"
                  type="email"
                  placeholder="admin@example.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </Box>
              <Box>
                <FieldLabel>Retries</FieldLabel>
                <Input
                  size="sm"
                  type="number"
                  min={0}
                  value={retries}
                  onChange={(event) => setRetries(event.target.value)}
                />
              </Box>
              <Box>
                <FieldLabel>Retry delay (seconds)</FieldLabel>
                <Input
                  size="sm"
                  type="number"
                  min={0}
                  placeholder="300"
                  value={retryDelay}
                  onChange={(event) => setRetryDelay(event.target.value)}
                />
              </Box>
            </Grid>
          </Section>
        </Stack>
      </Grid>

      <Flex justify="flex-end" gap={2} mt={5}>
        <Button size="sm" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button size="sm" colorPalette="blue" disabled={!dagIdValid || !dateValid} onClick={save}>
          Apply
        </Button>
      </Flex>

      {showCron ? (
        <CronGeneratorModal
          value={schedule.startsWith("@") ? "" : schedule}
          onSave={setSchedule}
          onClose={() => setShowCron(false)}
        />
      ) : undefined}
    </Modal>
  );
};
