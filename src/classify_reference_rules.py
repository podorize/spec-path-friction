"""Conservative deterministic rules for longitudinal reference evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


CREATE_WORDS = re.compile(r"\b(create|add|introduce|implement|scaffold|generate|write)\b", re.I)
RETIRE_WORDS = re.compile(r"\b(delete|remove|retire|deprecat|rename|move|replace|drop)\w*\b", re.I)
NON_FILE_MARKERS = re.compile(r"[*?{}\[\]]|(^|/)\.\.(/|$)")


def _result(decision: str, classification: str | None, rule_id: str, rationale: str, missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "decision": decision,
        "classification": classification,
        "rule_id": rule_id,
        "rationale": rationale,
        "missing_evidence": missing or [],
    }


def _text(record: dict[str, Any]) -> str:
    commit = record.get("anchor_commit_observation", {}).get("message", "")
    task = record.get("anchor_task_observation", {}).get("content_excerpt", "")
    context = record.get("task_context", "")
    return f"{context}\n{task}\n{commit}"


def _feature_tokens(path: str) -> set[str]:
    basename = Path(path).stem
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|[0-9]+", basename)
    ignored = {"test", "tests", "spec", "equivalence", "component", "service", "controller"}
    return {part.lower() for part in parts if len(part) >= 3 and part.lower() not in ignored}


def _path_history(record: dict[str, Any], relation: str) -> list[dict[str, Any]]:
    return [item for item in record.get("path_history_observation", {}).get("commits", []) if item.get("relation_to_anchor") == relation]


def classify_record(record: dict[str, Any]) -> dict[str, Any]:
    literal = record.get("literal_path_observation", {})
    candidate = record.get("resolved_candidate_observation", {})
    tree = record.get("repository_tree_observation", {})
    gaps = list(record.get("evidence_gaps", []))
    path = str(record.get("literal_code_path", ""))
    text = _text(record)
    commit_text = str(record.get("anchor_commit_observation", {}).get("message", ""))

    if literal.get("status") == "found" or candidate.get("status") == "found":
        return _result("classified", "confirmed_exists", "R1_EXISTS", "The literal or resolved candidate path exists at the anchor commit.")
    if NON_FILE_MARKERS.search(path):
        return _result("classified", "non_file_reference", "R2_PATTERN", "The reference contains glob, traversal, or pattern syntax and does not identify one unique file.")
    if gaps and (literal.get("status") == "inaccessible" or tree.get("status") in {"inaccessible", "http_error"}):
        return _result("abstain", "inaccessible_or_invalid", "R3_INACCESSIBLE", "Core anchor evidence could not be retrieved.", gaps)

    mentions = [mention.lower() for mention in record.get("explicit_repository_mentions", [])]
    current_repo = str(record.get("repo_name", "")).lower()
    external = [mention for mention in mentions if mention != current_repo]
    if external:
        return _result("classified", "external_repository_reference", "R4_EXTERNAL_REPO", f"The task explicitly names a different repository: {', '.join(external)}.")

    local_window = text
    basename = Path(path).name
    position = text.lower().find(basename.lower()) if basename else -1
    if position >= 0:
        local_window = text[max(0, position - 500): position + len(basename) + 500]
    retire_near_reference = bool(RETIRE_WORDS.search(local_window))
    retire_in_matching_commit = bool(
        RETIRE_WORDS.search(commit_text)
        and any(re.search(rf"\b{re.escape(token)}\b", commit_text, re.I) for token in _feature_tokens(path))
    )
    if retire_near_reference or retire_in_matching_commit:
        return _result(
            "classified",
            "expected_absence_move_or_delete",
            "R5_LIFECYCLE_RETIRE",
            "Task or anchor-commit evidence explicitly describes deletion, retirement, replacement, move, or rename near the reference.",
        )
    if _path_history(record, "after_anchor") and CREATE_WORDS.search(local_window):
        return _result(
            "classified",
            "expected_absence_create",
            "R6_CREATED_AFTER",
            "The task describes creation and exact-path history shows the file after the anchor commit.",
        )

    matches = tree.get("matching_paths_at_anchor", [])
    if len(matches) == 1 and matches[0] != path:
        return _result("requires_llm", None, "R7_SINGLE_BASENAME_CANDIDATE", "One same-basename candidate exists at the anchor, but semantic equivalence requires interpretation.")
    if "/" not in path and not matches:
        return _result("abstain", "ambiguous_reference", "R8_BARE_FILENAME", "A bare filename is absent and no unique same-basename candidate is available.")
    return _result("requires_llm", None, "R9_UNRESOLVED", "The deterministic evidence does not support a high-precision classification.", gaps)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    outputs = [{"review_id": record["review_id"], **classify_record(record)} for record in records]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in outputs), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in outputs:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    print(json.dumps({"records": len(outputs), "decisions": counts}, indent=2))


if __name__ == "__main__":
    main()
