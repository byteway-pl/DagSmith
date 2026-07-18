# DagSmith

**A visual, block-based DAG editor for Apache Airflow 3 — right inside the Airflow UI.**

DagSmith is an Airflow plugin (Airflow ≥ 3.1) that adds a full DAG editor to the
Airflow web UI:

- 🧱 **Visual editor** — build DAGs from blocks: drag operators from a searchable
  palette onto a canvas, connect them with dependency edges (tasks *and* TaskGroups),
  configure parameters in typed forms (key:value editors for dicts, a rich-text editor
  for HTML fields, connection pickers for `conn_id`s, a cron builder for schedules).
- ✍️ **Code editor** — edit the `.py` files in CodeMirror with syntax and import
  validation before anything is deployed.
- 🔁 **Two-way sync, code is the source of truth** — canvas edits are applied to your
  file as *minimal, surgical changes* (via [libcst](https://github.com/Instagram/LibCST));
  comments and formatting you didn't touch stay byte-for-byte identical. Editing the
  code updates the canvas. Dynamic constructs (loops, `.partial().expand()`) appear as
  code-only blocks instead of breaking the parser.
- 🧰 **Auto-generated operator palette** — installed provider packages are introspected
  (operators, sensors, their `__init__` signatures across the class hierarchy), so
  hundreds of blocks with typed parameter forms appear without any manual definitions.
- 💾 **Draft → Deploy** — work-in-progress is saved as versioned drafts in the Airflow
  metadata database (with autosave, history, diffs and restore). The live `.py` file
  changes **only** when you hit Deploy, after validation, with a backup and conflict
  detection. The scheduler never sees half-finished work.
- 👥 **Teams** — give each team a directory in a DAG bundle and a git repository:
  members-only editing, per-DAG reassignment by admins, team-tagged DAGs, and a
  *Commit & push* button (GitHub/GitLab) plus optional push-on-deploy.
- 🔒 **Safety by default** — deploy is disabled until explicitly enabled, all endpoints
  are authorized through the Airflow Auth Manager, user code is only ever executed in
  an isolated subprocess, every path is confined to the bundle root, and every deploy
  is audit-logged.

## Requirements

| Component | Version |
|---|---|
| Apache Airflow | **≥ 3.1** (uses the `react_apps` + `fastapi_apps` plugin APIs; no Airflow 2.x support) |
| Python | ≥ 3.10 |
| Metadata DB | PostgreSQL recommended (DagSmith stores drafts in its own `dagsmith_*` tables) |
| File access | to deploy, the Airflow api-server needs write access to the DAG bundle directory; working on drafts needs no file access at all |

## Installation

```bash
pip install dagsmith   # in the environment running the Airflow api-server
```

The plugin registers itself via the `airflow.plugins` entry point — don't copy anything
into `$AIRFLOW_HOME/plugins`. After restarting the api-server, **DagSmith** appears in
the Airflow navigation. Its `dagsmith_*` tables are created automatically on startup
(or run `python -m dagsmith db upgrade` manually).

### Enabling deploy

For safety, writing `.py` files is **off by default** — without it DagSmith works in
read-and-draft mode. Enable it consciously:

```ini
[dagsmith]
deploy_enabled = True
# optional hardening / team split:
# editors   = data-platform-team     # who can create and edit drafts
# deployers = admin                  # who can write .py files
# admins    = admin                  # who manages teams
# git_commit = True                  # commit to the bundle checkout on deploy
```

(or `AIRFLOW__DAGSMITH__DEPLOY_ENABLED=True` etc.)

> ⚠️ **Security note:** deploying DAGs from the UI is equivalent to executing arbitrary
> code in your Airflow environment — exactly like shipping a DAG file any other way.
> Enable `deploy_enabled` only with proper access control on the Airflow UI. Import
> validation executes the file's top level in an isolated, time-limited subprocess.

## How it works

```
Airflow UI ─▶ react_app "DagSmith" (React Flow canvas + CodeMirror)
                    │  REST /dagsmith/api/v1 (Airflow JWT)
                    ▼
             FastAPI app inside the api-server
                    │  parse (libcst) / codegen / validation (subprocess)
       ┌────────────┴────────────┐
  Save / autosave           Deploy (validated)
       ▼                        ▼
 Airflow metadata DB       .py files in the DAG bundle
 (draft versions,          (atomic write, backup,
  canvas layout)            conflict detection, git)
```

Three tiers of support for existing code:

1. **DAGs created in DagSmith** — full visual editing with remembered layout.
2. **Typical hand-written DAGs** (`with DAG(...)`, `@dag`, `@task`, `>>`, `chain()`,
   nested TaskGroups, edge `Label`s) — full visual editing without touching your
   formatting.
3. **Dynamic constructs** (task-generating loops, `.expand()`) — shown on the canvas as
   read-only blocks, editable in the code view.

## Development

```bash
pip install -e ".[dev]"
pytest                                # backend (incl. byte-exact round-trip corpus)
cd frontend && npm install
npm run build                         # UMD bundle -> src/dagsmith/static/
npm test && npm run lint
```

The frontend follows Airflow's AIP-68 react-plugin contract (single UMD bundle, host
provides React); everything ships inside the bundle — no CDNs.

## Support the project

If DagSmith saves you time, you can [buy me a coffee](https://buymeacoffee.com/byteway) ☕

## License

[Apache-2.0](LICENSE)
