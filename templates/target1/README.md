# HUF App Builder Templates

These JSON templates are starting points for scaffolding a HUF App — a provider Frappe app that seeds itself into the HUF platform.

## File Structure

All seed files must be placed flat (no subdirectories) under the app's seed directory:

```
apps/<myapp>/<myapp>/huf/
├── apps/*.json           → manifest files
├── prompts/*.json        → Agent Prompt records
├── tools/*.json          → Agent Tool Function records
├── knowledge/*.json      → Knowledge Source records
├── agents/*.json         → Agent records
└── triggers/*.json       → Agent Trigger records
```

The scanner (`find_seed_dirs()`) prefers the Python package root location and is **non-recursive** — files placed in subdirectories are silently ignored with no error.

## Usage

1. Copy a template file to its target location in your app.
2. Replace all `ALL_CAPS` and `<angle-bracket>` placeholders with real values.
3. For `manifest.json.template`: ensure the `app_id` is globally unique by checking `huf.ai.apps_api.get_huf_apps` before use. Collisions do not fail loudly; a duplicate `app_id` leaves a note in the existing app's `sync_error` while the new manifest is silently dropped.
4. All other seeds may reference each other by their key fields (e.g., `agent_name`, `tool_name`) as long as they are in the same app and seed pass.

## Synchronization

After placing seed files, sync them into HUF:

**Via bench CLI:**
```bash
bench --site <site> execute huf.ai.app_seeding.seeder.on_app_installed --args "['<myapp>']"
```

Or for just the app manifest:
```bash
bench --site <site> execute huf.ai.app_seeding.apps_loader.sync_huf_apps
```

**Via API (System Manager only):**
```bash
curl -X POST "$SITE/api/method/huf.ai.apps_api.sync_huf_apps" \
  -H "Authorization: token $KEY:$SECRET"
```

Then inspect the `sync_status` and `sync_error` fields on the `HUF App` record to verify success.

## Further reading

The templates here (and `AGENT_CONFIG_REFERENCE.md` next to this file) are self-contained for
scaffolding. For deeper platform background, the HUF repo itself documents this in
`doc/features/apps/manifest.md`, `doc/features/apps/app-pattern.md`, and
`doc/features/apps/seeding-and-hooks.md` — this skill repo doesn't vendor copies, so only follow
these if you have that repo checked out alongside the site you're seeding into.
