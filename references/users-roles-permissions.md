# Users, roles and permissions

Read when the app needs specific people or roles to use it, or when a step would change who can do what.

Availability: the capability model and the APIs below are **[available]** on the integration branch read for this page (`huf-flowfix`, branch `fix/flow-ui-schema-alignment`). Everything here is **Indicative: verify against the target build at build time** (`huf/permissions.py`, `huf/ai/permissions_api.py`).

Rule of this page: the skill describes access; it does not change it. Creating users, roles and grants is an owner action.

## 1. Default roles

Do not copy the lists into your app. Point to `huf/permissions.py` and read it on the target build:

- `CAPABILITIES` (permissions.py:30): every capability string with its label.
- `DEFAULT_ROLE_CAPABILITIES` (permissions.py:92): what each default role holds. Default roles on this build: Huf Admin (everything; backed by Frappe System Manager), Huf Manager, Huf User, Huf Viewer, Huf Gateway User (agent use only, meant for gateway `execution_user`).
- `get_user_huf_role` (permissions.py:201): System Manager and Administrator resolve to Huf Admin; otherwise the user's enabled Huf User Role; otherwise a fallback to the Frappe roles of the same names.

Never describe the defaults from memory; they change between builds.

## 2. Capabilities per feature (what to ask the owner for)

Group a feature's needs into the smallest set. Capability names are from `CAPABILITIES`; check each on the target build.

| App feature | Capabilities the users need |
|---|---|
| Chat with the agent | `agent.use`, `chat.use`, `chat.view_own` |
| See everyone's conversations | `chat.view_all` |
| Build or edit agents | `agent.create`, `agent.edit` (`agent.delete`, `agent.view_all` separately) |
| Knowledge | `knowledge.use` to search; `knowledge.create` / `knowledge.manage` to add or change |
| Tools | `tools.use`; `tools.create` / `tools.manage` |
| Flows | `flows.use`, `flows.create`, `flows.manage`; publishing flows with document triggers or web requests needs `flows.publish_sensitive`, flows that run code `flows.execute_code` |
| Data tables | `data.tables.manage`; records `data.records.create`, `.view_own`/`.view_all`, `.edit_own`/`.edit_all` |
| Channel replies | `channels.reply` |
| Usage analytics | System Manager, Huf Admin/Manager, or `agent.view_all` (`_require_analytics_access`, run_analytics_api.py:57) |

Sensitive capabilities, never to be put in a role an app proposes without a named owner decision: `roles.manage`, `users.invite`, `users.manage`, `developer.keys.manage`, `execution.approve`, `code_execution.run`, `ssh.run`, `ssh.approve`, `docker.run`, `execution_profile.manage`, `network_access_policy.manage`, `ssh_connection.manage`, and every `system.*`.

## 3. Users: owner-run only

`invite_user(email, full_name, huf_role)` (huf/ai/permissions_api.py:91, whitelisted):

- needs `users.invite`; refuses to change the caller's own role unless the caller is Administrator or System Manager (`_guard_self_targeting`, :54);
- creates a Frappe User of type System User with `send_welcome_email` 0 (no welcome email at insert) and no password, then a Huf User Role with `enabled` 1;
- `_require_all_capabilities` (:36) compares the caller with `DEFAULT_ROLE_CAPABILITIES` only, so for a custom role it checks nothing. Do not rely on it as a safety net.

Related: `update_user_role` (:155) and `set_user_enabled` (:184) need `users.manage`; `get_users` (:68) needs `users.manage`.

The agent must not call any of these, must not insert `User`, `Huf User Role` or Frappe `User Permission` documents, must not set passwords, and must not put user emails in seeds or fixtures (Frappe fixtures export users). Instead, tell the owner which role is needed and give them the command to run (placeholders only):

```bash
bench --site <SITE> execute huf.ai.permissions_api.invite_user \
  --kwargs '{"email": "<USER_EMAIL>", "full_name": "<FULL_NAME>", "huf_role": "<HUF_ROLE>"}'
```

The owner can instead use the Huf UI if the target build exposes a users screen. Test users on a local development bench the owner named are fine with test values and explicit approval, but never in files that ship.

## 4. Roles: agent drafts, owner approves and runs

`create_huf_role(role_name, description, capabilities)` (:251) and `update_huf_role(role_name, capabilities, description)` (:280) both need `roles.manage`. They reject unknown capability names. `update_huf_role` **replaces** the whole capability set, so read the current set first. `get_huf_roles` (:211) needs `users.manage` or `roles.manage`; `get_capabilities_catalogue` (:239) needs `roles.manage`.

What the agent may do:

1. Propose a role in prose or a table: name, purpose, and each capability with the feature that needs it.
2. Keep it least-privilege: start from `agent.use`, add only what a feature in section 2 requires, exclude every sensitive capability above unless the owner names it.
3. Stop for approval. Only after a clear yes in chat does the owner (or the agent, if the owner explicitly told it to and the session user holds `roles.manage`) run:

```bash
bench --site <SITE> execute huf.ai.permissions_api.create_huf_role \
  --kwargs '{"role_name": "<ROLE_NAME>", "description": "<WHY>", "capabilities": ["agent.use", "chat.use", "chat.view_own"]}'
```

Never grant System Manager or Huf Admin to anyone, and never edit a default role to "make it work".

## 5. What an app ships

- List the roles the app needs in the app README ("Required roles: Huf User for chat; Huf Manager for editing the knowledge source"), with the capabilities from section 2. Name default roles where one fits.
- Do not ship roles in `fixtures`, do not ship Huf User Role rows, do not ship Frappe User Permissions.
- Agent access fields (`allow_guest`, `allowed_users`, `allowed_roles`, `allow_chat`) live on the Agent. Seed `allow_guest` as 0. Guest access means anyone who can reach the API can run the agent, and allowed users/roles are not evaluated for unauthenticated callers (the field description in `agent.json`); setting it to 1 is an owner decision.
- Row-level restrictions with Frappe User Permissions are an owner configuration, not an app default.
- A gateway `execution_user` is a dedicated low-privilege user (Huf Gateway User role), never Administrator: see `references/gateways-and-whatsapp.md`.

## 6. Reads that are safe

Reading the default role map from `huf/permissions.py`, reading the site's roles (`get_huf_roles`, if the session user is permitted), and checking what the current session can do. Do not call any write function above to "test" it.
