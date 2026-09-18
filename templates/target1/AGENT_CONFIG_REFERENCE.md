# Agent Config Reference

Index of every `Agent` DocType field relevant to scaffolding, grouped by capability.
Source of truth: `huf/huf/huf/doctype/agent/agent.json`. Only set a field if the plan
actually calls for that capability — leave the rest at their default (shown below).

Multi-run/planning fields (`enable_multi_run`, `default_plan`) are intentionally
excluded — out of scope for this skill.

| Group | Field | Type | Default | What it does |
|---|---|---|---|---|
| **Identity & Prompt** | `agent_name` | Data | — | Unique agent name |
| | `provider` / `model` | Link | — | AI Provider / AI Model to run on |
| | `prompt_mode` | Select | Local | `Local` = use `instructions`; `Template` = link `agent_prompt` |
| | `agent_prompt` | Link | — | Reusable Agent Prompt (when `prompt_mode=Template`) |
| | `instructions` | Code | — | The system prompt (when `prompt_mode=Local`) |
| | `temperature` / `top_p` | Float | 1 / 1 | Sampling params — tune one, not both |
| | `description` | Small Text | — | Short summary of what the agent does |
| | `starter_prompts` | Table | — | Up to 3 example prompts shown in chat |
| **Vision / Document Upload** | `allow_file_upload` | Check | 0 | Let users attach files/images in chat |
| | `enable_ocr` | Check | 0 | Route uploads through OCR instead of vision/local extraction |
| | `max_upload_size_mb` | Int | 25 | Per-file cap, capped globally at 25MB |
| **Image Generation** | `image_generation_model` | Link | — | Model for the image-gen tool; falls back to provider default if unset |
| **Audio: STT/TTS** | `stt_model` | Link | — | Speech-to-text model for audio transcription |
| | `tts_model` / `tts_voice` | Link / Data | — | Text-to-speech model + voice (e.g. `alloy`, `echo`, `onyx`) |
| **Context & Summarization** | `context_strategy` | Select | Summarize | `Summarize` (LLM-compress old messages) / `FIFO` (drop oldest) / `None` |
| | `history_limit` | Int | 20 | Messages before the strategy triggers |
| | `summary_ratio` | Float | 0.7 | Fraction of history compressed |
| | `summary_model` | Link | — | Dedicated (often cheaper) model for summarization |
| | `summary_prompt_mode` / `summary_prompt_template` / `summary_prompt` | Select/Link/Code | Local | Same Local-vs-Template pattern as the main prompt |
| | `max_knowledge_tokens` | Int | 4000 | Token budget for injected knowledge context |
| | `max_turns` | Int | 20 | Max consecutive tool/action turns per run |
| **Reasoning** | `reasoning_mode` | Select | Auto | `Auto` / `On` (force) / `Off` (disable) |
| | `reasoning_effort` | Select | Auto | `Auto` / `Low` / `Medium` / `High` |
| | `reasoning_budget_tokens` | Int | — | Explicit thinking-token budget (Anthropic extended thinking) |
| | `reasoning_summary` | Select | None | `None` / `Concise` / `Detailed` (Response-API models) |
| **Prompt Caching** | `enable_prompt_caching` | Check | 0 | Only OpenAI/Anthropic/Bedrock/Deepseek |
| | `cache_control_type` | Select | ephemeral | `ephemeral` (Anthropic) / `auto` (OpenAI/Deepseek) |
| | `cache_system_message` / `cache_conversation_history` | Check | 1 / 0 | What gets cached |
| **Memory** | `enable_memory` | Check | 0 | Long-term scoped memory |
| | `memory_policy` | Link | — | Memory Policy governing capture/retrieval |
| | `enable_memory_search_tool` / `enable_memory_write_tool` | Check | 1 / 1 | Auto-grant search/write memory tools |
| **Conversation Data** | `enable_conversation_data` | Check | 0 | Let the agent store key-value pairs in conversation context |
| | `inject_conversation_data` | Check | 1 | Auto-inject stored data into every prompt turn (costs tokens) vs. on-demand tool access only |
| | `conversation_data_api_permission` | Select | — | `` (none) / `Read` / `Write` via external API |
| **Tools, MCP & Execution** | `agent_tool` | Table | — | Attached Agent Tool Functions |
| | `agent_mcp_server` | Table | — | External MCP servers for extra tools |
| | `allow_code_execution` / `execution_profile` | Check / Link | 0 | Python code-exec tool; stays inert without both set |
| | `allow_ssh` / `ssh_connections` | Check / Table | 0 | Allowlisted SSH access |
| | `max_context_chars` | Int | 2000 | Truncation limit for tool results |
| **Knowledge & Skills** | `agent_knowledge` | Table | — | Attached Knowledge Sources |
| | `agent_skill` | Table | — | Attached reusable Skill bundles |
| **Permissions** | `allow_chat` | Check | 0 | Usable in the Agent Chat window |
| | `allow_guest` | Check | 0 | Runnable by Guest users via API |
| | `allowed_users` / `allowed_roles` | Table MultiSelect | — | Access restriction lists |
| | `persist_conversation` | Check | 1 | Save/reload chat history across sessions |
| | `persist_user_history` | Check | 1 | Per-user history for Doc Event/Scheduled runs vs. one shared history |
| **Runtime** | `async` / `run_immediately` | Check | 0 / 0 | Queue in background vs. run inline on submit |
| | `disabled` | Check | 0 | Kill switch |
| | `autonaming_of_conversation_title` | Check | 1 | Auto-title new conversations |

## How to use this in a plan

1. In Step 1 (Discover), ask which capability groups above the agent actually needs —
   don't assume none beyond the base prompt.
2. In Step 2 (Plan), list only the non-default fields the plan requires, with values,
   grouped the same way as this table.
3. In Step 3 (Execute), set those fields in `agent.json.template`'s seed file. Leave
   every other field at its default — do not set fields "just in case."
