#!/usr/bin/env python3
"""Read-only check of Huf app seed files (agents, prompts, tools, knowledge, triggers).

Usage:
  python3 scripts/validate_agent_seed.py [--huf-repo /path/to/huf-checkout] [paths ...]

Paths are seed files or a seed directory (<myapp>/huf/ with agents/, prompts/, tools/,
knowledge/, triggers/ subfolders; scanning is flat, like the Huf seeder). With no paths it
checks templates/target1/*.json.template that are seed shapes.

Checks:
  1. Every key exists as a field of the target doctype (needs --huf-repo; the doctype JSON is read
     from <repo>/huf/huf/doctype/<name>/<name>.json, or <repo>/huf/doctype/... for a package root).
     Keys starting with "_" are comments. Agent "tools" and "knowledge" are the seeder's own shortcuts.
  2. Names listed in an agent's tools / knowledge exist as seed files in the sibling folders
     (a name that is not seeded may still exist on the site: reported as WARN).
  3. Key-like strings (provider key prefixes, long token-looking values, private key blocks) and
     secret-named fields with values: ERROR.
  4. allow_guest set to 1: WARN (owner decision). <PLACEHOLDER> values in provider/model: WARN
     (must be replaced by names that exist on the target site before sync).
Exit code 1 when any ERROR is found. Nothing is written, no network, stdlib only.
Indicative: verify against the target build's doctype JSON at build time.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# seed folder -> (doctype, doctype folder name, key field)
KINDS = {
	"agents": ("Agent", "agent", "agent_name"),
	"prompts": ("Agent Prompt", "agent_prompt", "title"),
	"tools": ("Agent Tool Function", "agent_tool_function", "tool_name"),
	"knowledge": ("Knowledge Source", "knowledge_source", "source_name"),
	"triggers": ("Agent Trigger", "agent_trigger", "trigger_name"),
}
AGENT_SHORTCUTS = {"tools", "knowledge"}
STANDARD_KEYS = {"doctype", "name", "source_app", "source_file", "docstatus"}
LAYOUT = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading"}

KEY_PATTERNS = [
	re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
	re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
	re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{20,}"),
	re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
	re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
	re.compile(r"\bEAA[A-Za-z0-9]{40,}"),
	re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
	re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
]
SECRET_NAME = re.compile(r"(api_?key|secret|password|token|passwd|credential)", re.I)
PLACEHOLDER = re.compile(r"^<[A-Za-z0-9_ -]+>$")
LONG_TOKEN = re.compile(r"^[A-Za-z0-9+/_=-]{32,}$")


class Report:
	def __init__(self) -> None:
		self.errors = 0
		self.warns = 0

	def error(self, where: str, msg: str) -> None:
		self.errors += 1
		print(f"ERROR {where}: {msg}")

	def warn(self, where: str, msg: str) -> None:
		self.warns += 1
		print(f"WARN  {where}: {msg}")


def doctype_fields(repo: Path | None, folder: str, cache: dict) -> set[str] | None:
	if repo is None:
		return None
	if folder in cache:
		return cache[folder]
	for base in (repo / "huf" / "huf" / "doctype", repo / "huf" / "doctype"):
		p = base / folder / f"{folder}.json"
		if p.is_file():
			meta = json.loads(p.read_text())
			cache[folder] = {f["fieldname"] for f in meta.get("fields", []) if f.get("fieldtype") not in LAYOUT}
			return cache[folder]
	cache[folder] = None
	return None


def walk_strings(value, path=""):
	if isinstance(value, dict):
		for k, v in value.items():
			yield from walk_strings(v, f"{path}.{k}" if path else k)
	elif isinstance(value, list):
		for i, v in enumerate(value):
			yield from walk_strings(v, f"{path}[{i}]")
	elif isinstance(value, str):
		yield path, value


def check_secrets(rep: Report, where: str, data) -> None:
	for path, text in walk_strings(data):
		leaf = path.rsplit(".", 1)[-1]
		if any(p.search(text) for p in KEY_PATTERNS):
			rep.error(where, f"key-like string in {path}")
		elif SECRET_NAME.search(leaf) and text.strip() and not PLACEHOLDER.match(text.strip()) and not leaf.startswith("_"):
			rep.error(where, f"secret-named field {path} has a value; use a <PLACEHOLDER> or leave it out")
		elif LONG_TOKEN.match(text) and not text.startswith("<") and " " not in text and "." not in text and "/" not in text[:1]:
			if any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
				rep.warn(where, f"long token-looking value in {path}; confirm it is not a secret")


def classify(path: Path) -> str | None:
	if path.parent.name in KINDS:
		return path.parent.name
	name = path.name.lower()
	for kind, stem in (("agents", "agent."), ("prompts", "prompt."), ("tools", "tool."), ("knowledge", "knowledge."), ("triggers", "trigger.")):
		if name.startswith(stem):
			return kind
	return None


def collect(paths: list[Path]) -> list[Path]:
	out: list[Path] = []
	for p in paths:
		if p.is_dir():
			subs = [p / k for k in KINDS if (p / k).is_dir()]
			if subs:
				for s in subs:
					out += sorted(s.glob("*.json"))
			else:
				out += sorted(p.glob("*.json"))
		else:
			out.append(p)
	return out


def seeded_names(files: list[Path]) -> dict[str, set[str]]:
	names = {k: set() for k in KINDS}
	for f in files:
		kind = classify(f)
		if not kind:
			continue
		try:
			d = json.loads(f.read_text())
		except (OSError, ValueError):
			continue
		if isinstance(d, dict) and d.get(KINDS[kind][2]):
			names[kind].add(str(d[KINDS[kind][2]]))
	return names


def check_file(rep: Report, f: Path, repo: Path | None, names: dict, cache: dict) -> None:
	where = str(f)
	try:
		data = json.loads(f.read_text())
	except (OSError, ValueError) as e:
		rep.error(where, f"cannot read JSON: {e}")
		return
	if not isinstance(data, dict):
		rep.error(where, "seed file must be a JSON object")
		return
	check_secrets(rep, where, data)
	kind = classify(f)
	if not kind:
		rep.warn(where, "cannot tell which doctype this seed is (put it in agents/, prompts/, tools/, knowledge/ or triggers/)")
		return
	doctype, folder, key_field = KINDS[kind]
	if not data.get(key_field):
		rep.error(where, f"missing key field '{key_field}'")
	fields = doctype_fields(repo, folder, cache)
	if fields is None:
		if repo is not None:
			rep.warn(where, f"{doctype} doctype JSON not found under --huf-repo; key check skipped")
	else:
		allowed = fields | STANDARD_KEYS | (AGENT_SHORTCUTS if kind == "agents" else set())
		for k in data:
			if k.startswith("_"):
				continue
			if k not in allowed:
				rep.error(where, f"'{k}' is not a field of {doctype}")
	if kind == "triggers":
		ag = data.get("agent")
		if ag and ag not in names["agents"]:
			rep.warn(where, f"agent '{ag}' is not among the seeded agents; fine only if it already exists on the site")
	if kind == "agents":
		for field, sibling in (("tools", "tools"), ("knowledge", "knowledge")):
			vals = data.get(field)
			if vals is None:
				continue
			if not isinstance(vals, list) or not all(isinstance(v, str) for v in vals):
				rep.error(where, f"'{field}' must be a list of names")
				continue
			for v in vals:
				if v not in names[sibling]:
					rep.warn(where, f"{field} entry '{v}' is not in the seed folder; fine only if it already exists on the site")
		if data.get("allow_guest") in (1, True, "1"):
			rep.warn(where, "allow_guest is 1: anyone who can reach the API can run this agent. Needs explicit owner approval")
		for pf in ("provider", "model", "stt_model", "tts_model", "image_generation_model"):
			v = data.get(pf)
			if isinstance(v, str) and PLACEHOLDER.match(v):
				rep.warn(where, f"{pf} is the placeholder {v}: replace with a name that exists on the target site, or remove the field")
		if "execution_profile" in data and data["execution_profile"]:
			rep.warn(where, "execution_profile is set: owner decision")


def main() -> int:
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("paths", nargs="*", type=Path)
	ap.add_argument("--huf-repo", type=Path, help="Huf checkout (for the doctype field lists)")
	args = ap.parse_args()

	if args.paths:
		files = collect(args.paths)
	else:
		files = sorted((ROOT / "templates" / "target1").glob("*.json.template"))
		files = [f for f in files if classify(f)]
	rep = Report()
	if args.huf_repo is None:
		rep.warn("(all files)", "--huf-repo not given: the field-name check was SKIPPED; only secret, link and access checks ran, so 0 errors is not a full pass")
	names = seeded_names(files)
	cache: dict = {}
	for f in files:
		check_file(rep, f, args.huf_repo, names, cache)
	print(f"{len(files)} file(s) checked: {rep.errors} error(s), {rep.warns} warning(s)")
	return 1 if rep.errors else 0


if __name__ == "__main__":
	sys.exit(main())
