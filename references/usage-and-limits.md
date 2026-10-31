# Usage and limits

Read when the owner asks how much the app may spend, how long a run may go, or where cost shows up.

Availability: **[available]** on the build read for this page, but every item is marked **[verify]**: confirm field names, defaults and function signatures on the target build before you rely on them. Changing any limit is an owner decision (SKILL.md Hard Constraints).

## 1. Run budget (site-wide)

Single doctype **Agent Settings**, section `run_budget_section` (huf/huf/doctype/agent_settings/agent_settings.json). Read and write: System Manager only. **[verify]**

| Field | Type | Default in the doctype | Meaning |
|---|---|---|---|
| `max_turns_ceiling` | Int | 20 | Upper bound on any agent's `max_turns` |
| `max_depth` | Int | 3 | How deep agent-calls-agent chains may go |
| `deadline_seconds` | Int | 900 | Wall-clock deadline for a run |
| `spend_cap_usd` | Currency | 0 | Cumulative cap for one run chain; **0 means unlimited** |

Enforcement is in `huf/ai/run_budget.py`: `RunBudget` and `RunBudgetExceeded`; the effective turns are `min(agent.max_turns or 10, ceiling or 20)` (:68-70); `spend_cap_usd` 0 is deliberately not coalesced (:71-75); `estimate_run_cost` is at :169. Note that code falls back to depth 5 when the stored value is empty (:40) while the doctype default is 3. **[verify]**

The skill recommends values and asks the owner. It does not set them.

## 2. Per-agent limits

On the Agent doctype (huf/huf/doctype/agent/agent.json). **[verify]** defaults on the target build.

| Field | Default | Meaning |
|---|---|---|
| `max_turns` | 20 | Turns per run, capped by `max_turns_ceiling` |
| `history_limit` | 20 | Messages of history sent to the model |
| `max_knowledge_tokens` | 4000 | Knowledge text added to context |
| `max_context_chars` | 2000 | Context size knob; read the field description on the build |
| `max_upload_size_mb` | 25 | Upload size per file |
| `execution_profile` | none | Link to an Execution Profile (code/SSH limits); owner decision |

Seed only values the plan calls for. Lowering `max_turns` and `history_limit` is the cheap way to bound cost for a small app.

## 3. Cost per run

Each run is an **Agent Run** document with `input_tokens`, `output_tokens`, `cached_tokens`, `total_tokens`, `cost` (Float), `cost_source` and `cost_calculation_status`. **[verify]** Cost comes from `huf/ai/cost_calculator.py` and `huf/ai/usage_extraction.py`, using the AI Model's pricing fields (`input_cost_per_1m_tokens`, `output_cost_per_1m_tokens`, cached variants; `use_custom_pricing` marks owner overrides). Cost is an estimate and may be missing for models without pricing; check `cost_calculation_status` before quoting a number.

## 4. Analytics

- `huf.ai.agent.run_analytics_api.get_execution_analytics` (run_analytics_api.py:145-146, GET, whitelisted). Parameters: `from_date`, `to_date`, `granularity` (`hour` or `day`), `dimension` (e.g. `provider`), `entity`. Gated by `_require_analytics_access` (:57): System Manager, Huf Admin/Manager, or `agent.view_all`. Windows are capped (`MAX_WINDOW_DAYS`). Returns summary, series, breakdowns. **[verify]**
- `huf.ai.agent.conversation_analytics_api.get_conversation_analytics(conversation)` (conversation_analytics_api.py:305, GET, whitelisted): per-conversation totals read straight from Agent Run; access is checked per conversation (`_require_conversation_access`). **[verify]**

Read-only example for the owner or an authorised session:

```bash
curl -s -H "Cookie: <SESSION_COOKIE>" \
  "https://<SITE>/api/method/huf.ai.agent.run_analytics_api.get_execution_analytics?granularity=day&dimension=provider"
```

## 5. What to put in the plan

State the expected model, the chosen `max_turns`, and the owner's answer to the Step 1 spend question. Tell the owner where to look afterwards: Agent Run `cost` and the analytics calls above. Never promise a cost figure; pricing churns.
