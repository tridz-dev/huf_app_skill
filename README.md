# huf-app-builder

An AI coding agent skill that helps you build apps on top of HUF. Works with
Claude Code, Codex, Cursor, OpenCode, Kimi, or any agent CLI that can read a
file, run shell commands, and write files — it's not tied to one tool.

## What is this skill?

It's a set of plain-language instructions (`SKILL.md`, plus some templates)
that turns "I want to build an app on HUF" into a working scaffold. Instead
of you figuring out the manifest format, the seed file layout, or the API
auth headers from scratch, the agent asks a few questions, shows you a plan,
and then writes the files.

## Using it with your agent

Claude Code, Codex CLI, Cursor, and Kimi Code all natively load skills the
same way: a directory containing `SKILL.md` with YAML frontmatter, placed in
that tool's skills root. OpenCode also auto-scans some of those same roots.

Run `./install.sh` from this directory — it symlinks this repo into every
skills root it finds on your machine (skipping any tool you don't have
installed):

```bash
./install.sh
```

| Harness | Skills root |
|---|---|
| Claude Code | `~/.claude/skills/` (or `.claude/skills/` in a project) |
| Codex CLI | `~/.codex/skills/` (or `~/.agents/skills/`) |
| Cursor | `~/.cursor/skills/` (or `.cursor/skills/` in a project) |
| Kimi Code | `~/.kimi-code/skills/`, or `extra_skill_dirs` in `config.toml` |
| OpenCode | auto-scans `~/.claude/skills/` and `~/.agents/skills/`; also `.opencode/skills/` or `skills.paths` in `opencode.json` |

No native skill loader for your tool? Copy the whole directory (not just
`SKILL.md` — it needs `templates/` alongside it) into your project and point
the agent at `SKILL.md`, or paste its contents in as a prompt.

It doesn't run any magic — it just knows the HUF app patterns cold and
follows them consistently.

## What is a HUF app?

HUF is an AI agent platform. A "HUF app" is any agent-powered app that plugs
into it. There are two ways to build one:

1. **Inside HUF** — you seed an Agent (with a prompt, knowledge, tools)
   directly into a HUF/Frappe bench. It shows up as a tile in HUF and users
   open it like any other app in the platform.
2. **Outside HUF** — your own app (a website, a Slack bot, a script,
   whatever) that talks to HUF over its REST API using an API key. HUF is
   just a backend you call.

## Who can use it

Anyone using an AI coding agent against a HUF/Frappe workspace — internal
developers building agent features, or anyone integrating an external
service with HUF's API. You don't need to know the HUF app internals
beforehand; the skill exists so you don't have to.

## How to use it

1. Install it (`./install.sh`, or see the table above).
2. Tell your agent what you want to build, e.g. "build a HUF app that
   summarizes support tickets."
3. It will ask:
   - What's the app for, and who uses it?
   - Does it need its own UI, or is it agent-only?
   - Does it need to be *launched from* HUF, or does it just need to
     *call* HUF? (this decides inside vs. outside)
   - Is this for your own use, or are you shipping it as an app for other
     people to install? (this changes how the prompt and knowledge get
     written — see below)
   - What real material (files, URLs, existing docs) should the agent be
     grounded in, if any?
4. It shows you a concrete plan — what gets created, which files, which
   API scopes, and a draft of the actual system prompt — and waits for your
   go-ahead.
5. It scaffolds the files with real content: the finished system prompt,
   and knowledge sources seeded from the material you actually gave it (or
   no knowledge seed at all if you said you'd add your own later — it won't
   make up knowledge content). For an inside-HUF app, it also checks the files sync
   correctly. For an outside-HUF app, it never touches your secret key — you
   copy that yourself from HUF's Developer Settings.

### Personal vs. shipped apps

If you say the app is **for yourself**, the prompt and knowledge can
reference your own team, tools, and data directly.

If you say you're **shipping it to others**, the skill writes the prompt as
generic install instructions (not "you, the builder") and refuses to seed
your own private docs or credentials into it — an app meant for someone
else's site should only ship with material that's safe to hand them.

### Beyond chat: vision, voice, memory, and more

An Agent isn't just a prompt. The skill also asks whether yours needs
document/vision upload, OCR, image generation, voice (STT/TTS), a custom
context/summarization strategy, reasoning control, prompt caching, memory,
or code execution/SSH tools — and sets only the fields each one needs. Full
index: [`templates/target1/AGENT_CONFIG_REFERENCE.md`](templates/target1/AGENT_CONFIG_REFERENCE.md).

### Connecting to other apps (CRM, ERPNext, HR, ...)

If the agent needs to read or write data in another installed app, the skill
discovers the real installed apps and DocTypes on your site first (`bench
list-apps`, then each DocType's live meta) instead of guessing field names
from general ERPNext/CRM knowledge — schemas vary by version and
customization.

## Examples

**Inside HUF**

- *Support ticket triage agent* — reads incoming tickets, tags them by
  urgency/category, drafts a reply. Seeded as an Agent + Prompt + Knowledge
  Source (your support docs), shows up as a tile in HUF.
- *Meeting notes agent* — takes a transcript, produces action items and a
  summary. Just an Agent + Prompt, no extra tools needed, launched from HUF.

**Outside HUF**

- *Slack bot* — a small external service that receives Slack messages,
  calls a HUF agent over the REST API to generate a reply, and posts it
  back. Uses an API key scoped to `agents:run` and `conversations:write`.

## What it won't do for you

- It won't run `bench new-app` — you create the Frappe app yourself, the
  skill only adds the HUF seed files into it.
- It won't create or reveal API keys — you mint those yourself in HUF's
  Developer Settings UI.
- It won't scaffold a Desk-page delivery — that path isn't supported by HUF
  yet, so the skill will tell you that instead of pretending it works.
