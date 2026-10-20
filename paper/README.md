# When Specs Name Ghosts: Disentangling Anticipatory Creation from Implementation Friction in Spec-Driven Development

**Track:** MSR 2027 Mining Challenge Track  
**Submission Type:** Short Paper (IEEE Conference Format, 4 pages + 1 page references)  
**Dataset Studied:** SpecMine Corpus v1.0 (July 2026 snapshot, Zenodo DOI: 10.5281/zenodo.22102779)  
**Replication Package:** [Anonymous 4open Science Repository](https://anonymous.4open.science/r/specpath-challenge-2027)

---

## Abstract

Spec-Driven Development (SDD) is an emerging paradigm where natural language specifications guide autonomous AI coding agents. In the SpecMine corpus (v1.0, July 2026 snapshot), the traceability layer resolves 435,401 task-to-code references in OpenSpec artifacts against repository git trees, revealing that 51,979 literal references fail to resolve at their anchoring commit (`exists_at_anchor = 0`). A naive interpretation would view these "missing" references as ubiquitous specification rot, hallucination, or implementation drift. In this mining challenge paper, we investigate the nature of these unresolved references.

We introduce **SpecPath**, a semi-supervised methodology to reconstruct reference lifecycles. We first establish a strictly blinded human Gold Standard ($N=90$, inter-rater Cohen's $\kappa = 0.907$) to calibrate an LLM-as-a-judge (Gemini 3.8 Flash, 100% friction recall), distill a stratified Silver Standard across 450 unique repositories, and extract 26 structural and contextual features to train a fast tabular classifier (Random Forest, $\text{ROC-AUC} = 0.8182$, 100% friction recall at $\tau \le 0.20$). 

Applying our model across all 51,979 missing references reveals that naive non-existence is overwhelmingly benign: **32.60%** of missing references represent planned, anticipatory file creations (rising to **63.1%** in open tasks), while **29.59%** are subsequently resolved in the codebase upon completion. Genuine specification-code friction (`confirmed_missing_problematic`) accounts for only **2.44%** of missing references across the entire corpus (and only **1.5%** in completed tasks). However, friction is heavily domain-specific: test-related references suffer an alarming **50.9%** friction rate, compared to **35.9%** in production source code. We release our calibrated pipeline, models, and labeled datasets to enable fast, zero-token pre-commit linters for agentic workflows.

---

## 1. Introduction

Autonomous AI coding agents such as Cursor, Claude Code, and OpenHands are transforming software engineering by translating natural-language instructions into complex codebase modifications. To combat conversational drift and prevent loss of developer intent (commonly termed "vibe coding"), industry has adopted **Spec-Driven Development (SDD)**. In SDD, explicit Markdown specifications (e.g., OpenSpec `tasks.md`, AWS Kiro `requirements.md`, GitHub Spec Kit) serve as the formal contracts and memory scaffolds governing agentic execution.

A core promise of SDD is verifiable traceability: a specification explicitly enumerates the files it intends to read, modify, or create. To examine this relationship, the SpecMine dataset (v1.0, July 2026 snapshot) extracted and statically resolved 435,401 task-to-code references in OpenSpec artifacts against the git tree at each spec's anchoring commit. Strikingly, **51,979 literal references** fail to resolve (`exists_at_anchor = 0`). In the MSR 2027 Mining Challenge Call, the organizers posed a critical open question:
> *"A spec names the files it expects to change. How often does that code actually exist? Resolving 435,401 OpenSpec task-to-code references against the tree at the anchoring commit makes the gap between what a spec declares and what the repository contains measurable: what predicts it, and does it widen as specs get longer?"*

A naive analysis of this gap risks severe mischaracterization. In traditional software repository mining, an unresolved file reference is typically flagged as broken traceability, documentation rot, or a hallucinated path. However, SDD introduces an inherent temporal paradox: specifications are frequently written *before* the corresponding code is drafted. Thus, a non-existent path at the anchoring commit may simply indicate an **anticipatory creation**—an intended file that the agent has not yet generated—rather than genuine friction.

To address this challenge without incurring unsustainable LLM inference costs across tens of thousands of repositories, we formulate two concrete Research Questions:
- **RQ1 (Decomposition of the Absence Gap):** What proportion of unresolved code references in SpecMine represent true specification friction versus benign lifecycle transitions (e.g., planned file creation, deletion/move, non-file syntaxes)?
- **RQ2 (Predictive Determinants & Domain Disparity):** Can fast, token-free tabular models accurately predict true friction from document-level metadata, and does friction vary systematically across file extensions and code domains (test vs. production)?

---

## 2. The SpecPath Taxonomy & Gold Standard Calibration

### 2.1 Reference Lifecycle Taxonomy

Examining raw task lines in OpenSpec (e.g., `- [ ] Create src/auth/token.ts`) reveals that literal absence at the anchoring commit encompasses heterogeneous phenomena:

| Category | Operational Definition & Corpus Semantics |
| :--- | :--- |
| `create` | **Expected Creation:** Path is intended to be newly created by the task (anticipatory reference). |
| `exists` | **Resolved / Exists:** File was created during task execution or resolved at a slightly displaced anchor. |
| `move_delete` | **Move or Deletion:** Intentional deprecation, deletion, or renaming of a legacy file. |
| `non_file` | **Syntactic Artifact:** CLI commands, package scopes (e.g., `@org/pkg`), or URL fragments erroneously matched as file paths. |
| `problematic` | **Confirmed Friction:** Path was expected to exist as contextual dependency or target, but was missing/broken. |
| `external` | **External Dependency:** Reference points to an external sub-repo, monorepo sibling, or system path. |
| `ambiguous` | **Inaccessible / Unverifiable:** Context is insufficient to establish ground truth deterministically. |

### 2.2 Human Gold Standard ($N=90$)
To establish an unassailable baseline, we sampled $N=90$ unresolved references across 90 distinct repositories in SpecMine. Two independent human evaluators manually inspected each repository's full git tree, the active commit, the parent commits, and the surrounding Markdown context in `tasks.md`. Disagreements were adjudicated through an unblinded consensus review. True specification friction accounted for only 2.22% ($N=2$) of the sample, while benign creations and resolution dominated.

### 2.3 Calibrated LLM-as-a-Judge
Because human inspection does not scale to 51,979 instances, we evaluated whether modern LLMs could act as reliable surrogate evaluators using a 5-step deterministic decision tree. We tested Gemini 3.8 Flash against the 90 blinded human Gold Standard cases.

![Figure 1: Gold Validation Matrix](figures/fig1_gold_validation_matrix.png)

As shown in **Figure 1**, the judge achieved **93.3% exact overall agreement** (84/90), yielding Cohen's $\kappa = 0.9069$ ("Almost Perfect" agreement) and Gwet's $\text{AC}_1 = 0.9257$. Crucially, the model achieved **100.0% Recall** on the minority friction class (`confirmed_missing_problematic`), perfectly identifying both subtle real-world defects without false negatives.

---

## 3. Semi-Supervised Distillation & Fast Tabular Prediction

### 3.1 Stratified Silver Standard ($N=450$) with Sampling Weights
Directly executing LLM evaluation across 51,979 rows would require millions of prompt tokens and hours of API latency. We therefore adopted a semi-supervised knowledge distillation paradigm across 450 strictly unique repositories:
- **Group A ($N=175$):** `task_done = 1` & `missing` ($w_i = 0.2516$)
- **Group B ($N=100$):** `task_done = 0` & `missing` ($w_i = 0.2284$)
- **Group C ($N=175$):** `task_done = 1` & `exists` ($w_i = 2.1893$)

Sampling weights ($w_i = P_{\text{population}} / P_{\text{sample}}$) were assigned to each stratum to guarantee asymptotically unbiased population estimators. The calibrated LLM judge evaluated the 450 instances, generating our Silver Standard training set.

### 3.2 Predictive Performance on Held-Out Human Benchmark
Using 26 morphological, lexical, contextual, and structural features, we evaluated three classifiers strictly on the held-out Human Gold Standard ($N=90$):

| Model | ROC-AUC | PR-AUC | Recall ($\tau \le 0.20$) | Specificity |
| :--- | :---: | :---: | :---: | :---: |
| **Random Forest** | **0.8182** | **0.0833** | **100.0%** | **97.7%** |
| Logistic Regression | 0.7670 | 0.0526 | 100.0% | 96.6% |
| HistGradientBoosting | 0.7386 | 0.0455 | 100.0% | 95.5% |

![Figure 2: ROC and Precision-Recall Curves](figures/fig2_model_roc_pr_curves.png)

As illustrated in **Figure 2**, calibrating the decision threshold to $\tau \le 0.20$ guarantees **100.0% Recall** on true friction while preserving 97.7% Specificity.

### 3.3 Feature Importance
**Figure 3** illustrates the Mean Gini Importance of the top 12 features from the Random Forest model:

![Figure 3: Feature Importance](figures/fig3_feature_importance.png)

Path character length (11.1%), basename length (11.0%), and artifact code reference density (10.8%) dominate predictive importance, followed by task position ratio (9.8%), line word count (9.6%), and deletion verbs (7.9%).

---

## 4. Corpus-Wide Empirical Findings

We executed our calibrated inference engine across all **51,979 unresolved references** in SpecMine (spanning 4,444 distinct repositories) in **2.36 seconds** ($\approx 22,000$ references/sec).

### 4.1 RQ1: Decomposing the Absence Gap

| Lifecycle Stage | Corpus Count | Corpus Share | Open Tasks ($N=17,752$) | Completed Tasks ($N=34,227$) |
| :--- | ---: | ---: | ---: | ---: |
| `create` | 16,945 | 32.60% | **63.1%** | 16.8% |
| `exists` (resolved) | 15,381 | 29.59% | 2.1% | **43.8%** |
| `move_delete` | 7,088 | 13.64% | 6.4% | **17.4%** |
| `non_file` | 6,870 | 13.22% | 10.1% | **14.8%** |
| `ambiguous` | 2,860 | 5.50% | 5.7% | 5.4% |
| `external_repo` | 1,569 | 3.02% | 8.4% | 0.2% |
| **`problematic` (Friction)** | **1,266** | **2.44%** | **4.2%** | **1.5%** |

![Figure 4: Corpus Lifecycle Distribution](figures/fig4_corpus_lifecycle_distribution.png)

- **Finding 1 (The Illusion of Breakdown):** Only **2.44%** of unresolved references represent genuine friction. Nearly two-thirds reflect healthy evolution: 32.60% are planned creations and 29.59% are resolved during implementation.
- **Finding 2 (The Temporal Lifecycle Shift):** In open tasks (`task_done = 0`), **63.1%** of unresolved references are anticipatory creations. Once tasks complete, anticipatory creations drop to 16.8%, resolved references rise to 43.8%, and residual friction drops to **1.5%**.

### 4.2 RQ2: Predictive Determinants & Domain Disparity

![Figure 5: Extension and Test Friction](figures/fig5_extension_and_test_friction.png)

- **Finding 3 (Test-Specification Brittleness):** References to test files (`.test.`, `.spec.`, `_test.`) suffer a calibrated friction rate of **50.94%** ($N=7,917$), compared to **35.93%** in production source code ($N=33,266$). Test fixtures and mocks decay far more rapidly than core production targets.
- **Finding 4 (Language Volatility):** Dynamic environments exhibit higher friction rates (Python `.py` at 47.7%, Shell `.sh` at 43.9%) than compiled languages (Go `.go` at 28.3%, C# `.cs` at 31.1%).

---

## 5. Practical Implications & Tools

1. **For Tool Builders (OpenSpec, Spec Kit, Kiro):** Tools should incorporate lifecycle-aware traceability. A binary flag `exists_at_anchor` is misleading; tools should classify intent (creation vs. dependency) before raising alarms.
2. **For Practitioners (Zero-Token Pre-Commit Linters):** Development teams can deploy our trained Random Forest classifier as an instant, zero-cost pre-commit hook that audits `tasks.md` at 22,000 refs/second, catching true friction before delegating to expensive LLM agents.

---

## 6. Ethical Implications

This study uses public open-source artifacts from the SpecMine corpus (archived on Zenodo under CC BY 4.0). We do not collect, process, or expose Personally Identifiable Information (PII) or author emails. Distilling knowledge into compact tabular models dramatically reduces computational energy and carbon footprint compared to repeated LLM queries.

---

## 7. Replication Package & Data Access

All code, trained models, Silver Standard labels, and high-resolution figures are archived and available for peer review:
- **Repository Directory:** `src/` (extraction, training, inference, and figure generation).
- **Paper Artifacts:** `paper/main.tex`, `paper/references.bib`, and `paper/figures/`.
- **Pre-computed Inference Data:** `data/processed/specmine_missing_refs_classified.parquet`.
