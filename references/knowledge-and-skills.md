# Knowledge, skills and prompt versions

Read when the agent needs grounding documents, an app-provided skill, or a prompt that can be versioned.

Availability: **[available]** on the build read for this page. Everything is **Indicative: verify against the target build at build time** (field lists, option values, function signatures). Surfaces not repeated here (skills hook, data tables) are in `references/platform-surfaces.md`.

## 1. Knowledge: seed SQLite FTS only

- Seed file `<myapp>/huf/knowledge/<id>.json`, keyed on `source_name` (loader: `upsert_knowledge`, huf/ai/app_seeding/loaders.py:172). Template: `templates/target1/knowledge.json.template`.
- Use `knowledge_type: "sqlite_fts"` with `storage_mode: "Frappe File"`. The loader also maps the older `"SQLite (FTS)"` spelling to that pair, and defaults `knowledge_type` to `sqlite_fts` when empty. `knowledge_type` options on this build: sqlite_fts, sqlite_vec, sqlite_hybrid, chroma, pgvector, redis, zvec, weaviate, faiss, pinecone.
- Seed only content the user supplied (SKILL.md Hard Constraints). Never seed private data into an app meant for other people.
- Vector backends (Chroma host, pgvector host and `pgvector_password` Password field, Pinecone and similar) belong to the owner: hosts, credentials and embedding providers are entered by a human in the UI. The skill does not write them, print them or put them in files. Use `test_connection` only after the owner has set them up.

## 2. Getting documents in: there is no upload API for the skill

Only these Knowledge methods are whitelisted (and so callable over `/api/method`):

| Method | Where | Use |
|---|---|---|
| `rebuild_index(knowledge_source)` | knowledge_source.py:154 | Queue a full re-index (sets status Rebuilding, runs on the long queue) |
| `test_search(knowledge_source, query, top_k=5)` | knowledge_source.py:174 | Run a real search against one source |
| `test_connection(knowledge_source)` | knowledge_source.py:184 | Check pgvector connection and embedding config |
| `reprocess_input(knowledge_input)` | knowledge_input.py:106 | Retry one input |

Adding content is a Desk/UI step: the owner opens the Knowledge Source and adds Knowledge Inputs (`input_type` File, Text or URL; a File input has an attach field). Equivalent, for scripts the owner runs: insert a **Knowledge Input** document (`knowledge_source`, `input_type`, plus `text` / `url` / `file`) and attach the file, then `rebuild_index`. Do not do that with private material unless the owner told you to, and do not invent a "upload" endpoint.

Input status values: Pending, Processing, Indexed, Error (`error_message` has the reason). Source status: Pending, Indexing, Ready, Error, Rebuilding. Index fields to read afterwards: `total_chunks`, `total_inputs`, `last_indexed_at`. `chunk_size` and `chunk_overlap` are on the source.

Permissions on this build: Knowledge Source write is System Manager and Huf Manager, read for Huf User. Using search at runtime needs `knowledge.use` (see `references/users-roles-permissions.md`).

## 3. Verify with test_search

After the owner adds content and the index is Ready:

```bash
bench --site <SITE> execute huf.huf.doctype.knowledge_source.knowledge_source.test_search \
  --kwargs '{"knowledge_source": "<SOURCE_NAME>", "query": "<A QUESTION THE DOCS CAN ANSWER>", "top_k": 3}'
```

Pass if the returned passages come from the supplied material. Empty results with status Ready usually mean the inputs did not index (check the Knowledge Input `status` and `error_message`). Report what came back; do not paste long document text into chat.

## 4. Skills

App skills load through the `huf_skills` hook and the sync in `huf/ai/skills/hooks.py` (see `references/platform-surfaces.md`, skills section). The doctype is **Skill**; writing it is System Manager only. Importing skills from git, a registry or a common destination (`huf/ai/skills/api.py`) fetches third-party instructions over the network: treat as untrusted and do it only when the owner asks.

## 5. Prompt versions

Agent Prompt is versioned. The whitelisted functions in `huf/ai/prompt_api.py`:

| Function | Capability checked |
|---|---|
| `create_new_version(prompt_name, prompt_body, title=None, description=None)` | `agent.create` |
| `fork_prompt(prompt_name, title=None)` | `agent.create` |
| `save_as_template(agent_name, title, category=None, visibility="Private", description=None)` | `agent.create` |
| `attach_template(agent_name, prompt_name, lock_version=0)` (:232) | `agent.edit` |
| `detach_from_template(agent_name)` | `agent.edit` |
| `get_version_history(prompt_name)` | `agent.use` |

(Summary-prompt twins exist, for example `attach_summary_template`.) `attach_template` switches the agent to Template mode; with `lock_version` 1 the agent stays on the version current at attach time (`prompt_version_locked`, `template_version_at_attach`), with 0 it follows new versions. `create_new_version` re-points linked agents through `_update_agent_links`, so it changes live agents: owner approval first on a live site. Category and visibility values: read the Agent Prompt Category doctype at build time. Seeding a prompt is just the seed file (`templates/target1/prompt.json.template`); use versioning calls only for changes after install.
