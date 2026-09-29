"""Create transparent lexical features for OpenSpec code references."""

from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openspec_code_refs.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "interim" / "reference_shape_features.parquet"


def main() -> None:
    con = duckdb.connect()
    input_sql = INPUT_PATH.as_posix().replace("'", "''")
    output_sql = OUTPUT_PATH.as_posix().replace("'", "''")

    con.execute(
        f"""
        COPY (
            SELECT
                id,
                repo_name,
                artifact_path,
                code_path,
                task_done,
                exists_at_anchor,
                resolved_path,
                CASE
                    WHEN code_path LIKE '../%' OR code_path LIKE './%'
                        THEN 'relative_path'
                    WHEN code_path LIKE '%*%' OR code_path LIKE '%?%'
                        THEN 'glob_pattern'
                    WHEN regexp_full_match(code_path, '\\.[A-Za-z0-9]+')
                        THEN 'extension_fragment'
                    WHEN code_path LIKE '%/%'
                        THEN 'project_relative_path'
                    ELSE 'bare_filename'
                END AS path_shape,
                code_path LIKE '%/%' AS has_directory,
                code_path LIKE '%*%' OR code_path LIKE '%?%' AS has_glob,
                code_path LIKE '../%' OR code_path LIKE './%' AS is_relative,
                regexp_full_match(code_path, '\\.[A-Za-z0-9]+') AS is_extension_fragment
            FROM read_parquet('{input_sql}')
        ) TO '{output_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    n_rows = con.execute(
        f"SELECT count(*) FROM read_parquet('{output_sql}')"
    ).fetchone()[0]
    print(f"Wrote {n_rows:,} references to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
