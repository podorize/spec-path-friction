# SpecPathFriction

**Investigating Code Path Traceability and Implementation Friction in Spec-Driven Development**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Replication package and research repository for the **MSR 2027 Mining Challenge** study analyzing the **SpecMine** corpus ([Agarwal et al., MSR 2027](https://arxiv.org/abs/2608.25202)).

---

## 1. Overview

In Spec-Driven Development (SDD), specification artifacts (such as OpenSpec `tasks.md`) frequently reference codebase paths to plan, track, and document implementation tasks. SpecMine provides an automated path-resolution signal (`exists_at_anchor = 0` vs. `1`) indicating whether literal code paths were present in repository snapshots at the anchor commit.

This research investigates the central methodological and empirical question:
> **When does an unresolved code path reference signal genuine implementation friction versus benign lifecycle transitions or noise?**

### Key Findings
1. **Literal Absence $\neq$ Implementation Defect:** Literal path absence (`exists_at_anchor = 0`) reflects benign lifecycle states in ~91% of cases (files to be created, intentional deprecations/moves, external repository references, or language-specific module layouts).
2. **Structural Associations:** Larger task lists (`log(n_tasks)`, OR = 1.54, $p < 0.001$) and lower completion rates (OR = 3.19, $p < 0.001$) are strongly associated with higher rates of unresolved references.
3. **Calibrated Semantic Prevalence:** In a design-weighted stratified English sample, only **8.9% – 9.1%** (95% bootstrap CI: 2.2% – 17.6%) of unresolvable path references represent genuine implementation friction (`confirmed_missing_problematic`).
4. **LLM as a High-Sensitivity Triage Instrument:** In evidence-equivalent evaluations (providing tree and history context), LLM judges achieve high recall (up to 100%) but moderate precision (~45.5%), making them suited as triaging aids rather than autonomous classifiers.
5. **Path Resolution Bottleneck:** Post-hoc audits show that human reviewers and automated tools often confuse cross-repo dependencies and module layout conventions (e.g., Rust `mod.rs` vs. `path.rs`, Go naming conventions) with missing code.

---

## 2. The 8-Class Semantic Taxonomy

To bridge the construct gap between literal string resolution and software friction, the project defines an 8-class taxonomy ([validation/PROTOCOL_V2_LONGITUDINAL.md](validation/PROTOCOL_V2_LONGITUDINAL.md)):

| Class | Definition |
|---|---|
| `confirmed_exists` | The referenced local implementation exists at the anchor commit. |
| `confirmed_missing_problematic` | A pre-existing local file is required but absent without a supported lifecycle or repository-boundary explanation. |
| `expected_absence_create` | A new local file is planned or appears after the anchor commit. |
| `expected_absence_move_or_delete` | The path was moved, renamed, replaced, deleted, or retired. |
| `external_repository_reference` | The reference denotes a file affirmatively located in another repository. |
| `non_file_reference` | The reference denotes something other than a unique file (glob, URL, package, documentation example). |
| `ambiguous_reference` | Available evidence does not support a safe decision. |
| `inaccessible_or_invalid` | Required evidence cannot be retrieved or validated. |

---

## 3. Repository Structure

```text
spec-path-friction/
├── data/
│   ├── raw/                 # Read-only SpecMine dataset parquet files (.gitkeep)
│   └── interim/             # Derived datasets, validation samples, review keys (.gitkeep)
├── src/                     # Python & Node.js automation pipeline
│   ├── build_longitudinal_evidence.py       # Longitudinal GitHub evidence collector
│   ├── classify_reference_rules.py          # Deterministic lifecycle and boundary rules
│   ├── create_*_workbook.mjs / import_*.mjs # Blinded Excel review workbook automation
│   ├── run_*_llm_judge*.py                  # Isolated LLM-as-a-judge execution runners
│   └── analyze_*.py                         # Statistical analyses, Wilson CIs, and bootstrap metrics
├── validation/              # Pre-registered protocols, design specs, prompts, and JSON schemas
│   ├── PROTOCOL_V2_LONGITUDINAL.md          # Primary longitudinal protocol
│   ├── HOLDOUT_V1_DESIGN.md                 # Two-phase holdout screening design
│   ├── LLM_JUDGE_PROMPT.md                  # Prompt for LLM semantic judge
│   └── llm_judge_output_schema_v2.json      # Structured output JSON schema
├── results/                 # Evaluation reports, confusion matrices, audit logs
│   ├── validation/holdout_v1/               # Two-phase holdout evaluation & Luna comparison
│   ├── validation/human_90_adjudicated/     # 90-case semantic adjudication & prevalence report
│   └── validation/evidence_equivalent_90/   # Evidence-equivalent audit reports
├── paper/                   # Research report and manuscript materials
└── tests/                   # Python unittest test suite
```

---

## 4. Setup and Execution

### Requirements
- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) (recommended) or standard virtualenv
- Node.js >= 18 (for Excel workbook generation scripts)

### Installation

```bash
# Clone the repository
git clone https://github.com/podorize/spec-path-friction.git
cd spec-path-friction

# Install dependencies using uv
uv sync
```

### Running Tests

```bash
uv run python -m unittest discover tests
```

---

## 5. Citation & Acknowledgments

This research builds upon the SpecMine dataset:
- S. Agarwal, A. Singhal, T. Breaux, B. Vasilescu, *"SpecMine: A Large-Scale Corpus of Spec-Driven Development Artifacts"*, MSR 2027 Challenge, arXiv:2608.25202.

---

## 6. License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
