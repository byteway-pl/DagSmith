import { Button, Flex, Input, Stack, Text, Textarea } from "@chakra-ui/react";
import { useState } from "react";

import { api, type DagTemplate } from "src/api/client";
import { Modal } from "src/components/Modal";

const starter = `# dagsmith: v1
from airflow.sdk import dag

@dag(dag_id="{{dag_id}}", schedule=None, catchup=False, tags={{tags}})
def {{dag_id}}():
    pass

{{dag_id}}()
`;

export const TemplateManager = ({ templates, onChange, onClose }: {
  templates: DagTemplate[]; onChange: () => Promise<void>; onClose: () => void;
}) => {
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [source, setSource] = useState(starter);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const select = (value: string) => {
    const template = templates.find((t) => t.id === value);
    setId(value); setName(template?.name ?? ""); setSource(template?.source ?? starter);
    setError("");
  };
  const save = async (remove = false) => {
    setBusy(true); setError("");
    try {
      if (remove) await api.deleteTemplate(id);
      else await api.saveTemplate(id, { name, source });
      await onChange();
      select("");
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  };
  return <Modal title="My DAG templates" wide>
    <Stack gap={3}>
      <select aria-label="Edit template" value={id} disabled={busy}
        onChange={(event) => select(event.target.value)}>
        <option value="">New template</option>
        {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
      <Input aria-label="Template name" placeholder="Template name" value={name}
        onChange={(event) => setName(event.target.value)} />
      <Text fontSize="sm">Personal templates are saved to your account. Use {"{{dag_id}}"} for the new DAG ID
        and {"{{tags}}"} for its tags (a Python list). Other Python braces are preserved.</Text>
      <Textarea aria-label="Template Python source" fontFamily="mono" rows={16} value={source}
        onChange={(event) => setSource(event.target.value)} />
      {error ? <Text color="red.solid">{error}</Text> : undefined}
      <Flex gap={2} justify="flex-end">
        {id ? <Button disabled={busy} colorPalette="red" onClick={() => {
          if (window.confirm("Delete this template? Existing DAGs will be kept.")) void save(true);
        }}>Delete</Button> : undefined}
        <Button variant="outline" disabled={busy} onClick={onClose}>Close</Button>
        <Button disabled={busy || !name.trim() || !source.trim()} onClick={() => void save()}>Save template</Button>
      </Flex>
    </Stack>
  </Modal>;
};
