#!/usr/bin/env python3
"""Validate Huf Flow definition JSON files against the Huf repo's graph IR schema.

Usage:
  python3 scripts/validate_flow_examples.py --huf-repo /path/to/huf [files or dirs ...]
  python3 scripts/validate_flow_examples.py --schema /path/to/graph_ir.schema.json [files ...]

With no files it checks templates/target1/examples/flows/*.json.
Each file is either a bare definition (schema_version/profile/nodes/...) or a record with
a "definition_json" key (like flow_definition.json.template).

Stage 1 (always): jsonschema (Draft 2020-12) against $defs/FlowGraph. Needs `pip install jsonschema`.
Stage 2 (only with --huf-repo): the repo's own validate_flow_graph in publish mode, offline.
  `frappe` is replaced by a stub when it is not installed; tool classification is faked
  (http_request counts as web, run_python as code), so no bench or database is needed.
Exit code 0 only when every file passes every stage that ran.
"""
from __future__ import annotations

import argparse
import importlib.abc
import importlib.machinery
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "templates" / "target1" / "examples" / "flows"


def _stub_frappe() -> None:
	try:
		import frappe  # noqa: F401
		return
	except ImportError:
		pass

	class _Loader(importlib.abc.Loader):
		def create_module(self, spec):
			m = MagicMock(name=spec.name)
			m.__path__ = []
			m.__spec__ = spec
			m.__name__ = spec.name
			return m

		def exec_module(self, module):
			pass

	class _Finder(importlib.abc.MetaPathFinder):
		def find_spec(self, name, path, target=None):
			if name == "frappe" or name.startswith("frappe."):
				return importlib.machinery.ModuleSpec(name, _Loader(), is_package=True)
			return None

	sys.meta_path.insert(0, _Finder())


def load_definition(path: Path) -> dict:
	data = json.loads(path.read_text(encoding="utf-8"))
	if isinstance(data, dict) and "definition_json" in data:
		data = data["definition_json"]
		if isinstance(data, str):
			data = json.loads(data)
	return data


def schema_errors(schema: dict, defn: dict) -> list[str]:
	from jsonschema import Draft202012Validator

	validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/FlowGraph"})
	return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator.iter_errors(defn)]


def repo_errors(huf_repo: Path, defn: dict) -> list[str]:
	sys.path.insert(0, str(huf_repo))
	_stub_frappe()
	from huf.ai.graph.permissions import ToolPermission
	from huf.ai.graph.validator import MODE_PUBLISH, validate_flow_graph

	def classify(tool_id):
		return ToolPermission(ptype=None, doctype=None, http=tool_id == "http_request", code=tool_id == "run_python")

	result = validate_flow_graph(defn, classify_tool=classify, mode=MODE_PUBLISH)
	return [f"{e.code} {e.node_id or ''} {e.field or ''}: {e.message}".strip() for e in result.errors]


def main(argv: list[str] | None = None) -> int:
	p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	p.add_argument("--huf-repo", type=Path, help="checkout of the huf app (gives the schema and the repo validator)")
	p.add_argument("--schema", type=Path, help="path to graph_ir.schema.json (stage 1 only)")
	p.add_argument("paths", nargs="*", type=Path)
	args = p.parse_args(argv)
	schema_path = args.schema or (args.huf_repo / "huf" / "ai" / "graph" / "graph_ir.schema.json" if args.huf_repo else None)
	if not schema_path or not schema_path.is_file():
		p.error("give --huf-repo or --schema pointing at the huf checkout's graph_ir.schema.json")
	schema = json.loads(schema_path.read_text(encoding="utf-8"))
	files: list[Path] = []
	for path in args.paths or [DEFAULT_DIR]:
		files.extend(sorted(path.glob("*.json")) if path.is_dir() else [path])
	if not files:
		p.error("no JSON files found")
	failed = 0
	for f in files:
		try:
			defn = load_definition(f)
			problems = schema_errors(schema, defn)
			stage2 = "skipped"
			if not problems and args.huf_repo:
				problems = repo_errors(args.huf_repo, defn)
				stage2 = "ok"
		except Exception as exc:  # unreadable file or missing import
			problems, stage2 = [f"{type(exc).__name__}: {exc}"], "n/a"
		if problems:
			failed += 1
			print(f"FAIL {f.name}")
			for line in problems:
				print(f"   - {line}")
		else:
			print(f"ok   {f.name}  (schema ok, repo validator {stage2})")
	return 1 if failed else 0


if __name__ == "__main__":
	raise SystemExit(main())
