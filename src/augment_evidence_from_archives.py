"""Fill missing repository-tree evidence using GitHub codeload archives."""

from __future__ import annotations

import json
import tarfile
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "interim" / "evidence_equivalent_90.jsonl"
OUTPUT = ROOT / "data" / "interim" / "evidence_equivalent_90_augmented.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines()]
    with tempfile.TemporaryDirectory(prefix="msr-codeload-") as tmp:
        tmp_path = Path(tmp)
        for index, row in enumerate(rows, start=1):
            tree = row["repository_tree_observation"]
            if tree.get("status") == "available":
                continue
            repo = row["repo_name"]
            sha = row["anchor_sha"]
            basename = tree.get("basename") or Path(row["literal_code_path"]).name
            url = f"https://codeload.github.com/{repo}/tar.gz/{sha}"
            archive = tmp_path / f"archive-{index}.tar.gz"
            request = Request(url, headers={"User-Agent": "msr2027-specmine-evidence-pilot"})
            try:
                with urlopen(request, timeout=90) as response, archive.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                paths = []
                with tarfile.open(archive, "r:gz") as tar:
                    for member in tar.getmembers():
                        if member.isfile() and Path(member.name).name == basename:
                            paths.append(member.name.split("/", 1)[-1])
                row["repository_tree_observation"] = {
                    "status": "available_archive",
                    "http_status": 200,
                    "basename": basename,
                    "matching_paths_at_anchor": paths[:100],
                    "match_count": len(paths),
                    "truncated": len(paths) > 100,
                    "source": "github_codeload_archive",
                }
                print(f"{row['review_id']}: archive tree ok ({len(paths)} matches)", flush=True)
            except (HTTPError, URLError, OSError, tarfile.TarError) as exc:
                row["repository_tree_observation"] = {
                    **tree,
                    "archive_status": "inaccessible",
                    "archive_error": type(exc).__name__,
                    "archive_url": url,
                }
                print(f"{row['review_id']}: archive failed ({type(exc).__name__})", flush=True)
    with OUTPUT.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Augmented evidence: {OUTPUT}")


if __name__ == "__main__":
    main()
