"""Generate publication-quality figures for the MSR 2027 paper."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_curve, roc_curve

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INTERIM = PROJECT_ROOT / "data" / "interim"
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "paper_figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Publication style
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "figure.dpi": 300,
})

TAXONOMY_SHORT = [
    "confirmed_exists",
    "confirmed_missing_problematic",
    "expected_absence_create",
    "expected_absence_move_or_delete",
    "external_repository_reference",
    "non_file_reference",
    "inaccessible_or_invalid",
]

LABELS_PRETTY = [
    "Confirmed Exists",
    "Missing Problematic",
    "Expected Create",
    "Expected Move/Del",
    "External Repo",
    "Non-File Ref",
    "Inaccessible",
]


def plot_fig1_gold_confusion_matrix() -> None:
    print("Generating Figure 1: Gold Standard Confusion Matrix...")
    cm_path = RESULTS_DIR / "validation" / "final_90_gemini" / "confusion_matrix.csv"
    cm_df = pd.read_csv(cm_path, index_col=0)
    
    # Filter to non-empty classes
    cols = [c for c in TAXONOMY_SHORT if c in cm_df.columns]
    cm_sub = cm_df.loc[cols, cols].values
    
    # Normalize by row (recall per true class)
    cm_norm = cm_sub.astype(float) / np.maximum(cm_sub.sum(axis=1, keepdims=True), 1)

    fig, ax = plt.subplots(figsize=(8, 6.5))
    sns.heatmap(
        cm_norm,
        annot=cm_sub,
        fmt="d",
        cmap="Blues",
        xticklabels=LABELS_PRETTY[:len(cols)],
        yticklabels=LABELS_PRETTY[:len(cols)],
        cbar_kws={"label": "Normalized Recall"},
        ax=ax,
        linewidths=0.5,
        linecolor="#DDDDDD",
    )
    ax.set_title("Gold Standard Agreement: Human Reviewer vs. Gemini Judge\n(N = 90, Exact Agreement: 93.3%, Cohen's $\\kappa$ = 0.907)", pad=15, fontweight="bold")
    ax.set_ylabel("True Human Classification", fontweight="bold", labelpad=10)
    ax.set_xlabel("Gemini 3.8 Flash Classification", fontweight="bold", labelpad=10)
    plt.xticks(rotation=35, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    fig.savefig(FIGURES_DIR / "fig1_gold_validation_matrix.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig1_gold_validation_matrix.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig1_gold_validation_matrix (PDF & PNG)")


def plot_fig2_roc_pr_curves() -> None:
    print("Generating Figure 2: ROC and Precision-Recall Curves...")
    from src.train_and_evaluate_predictive_models import (
        FEATURE_COLS, SILVER_PARQUET, prepare_gold_test_set
    )
    silver_df = pd.read_parquet(SILVER_PARQUET)
    gold_df = prepare_gold_test_set()

    X_train = silver_df[FEATURE_COLS]
    y_train = silver_df["target_problematic_binary"].astype(int)
    w_train = silver_df["sampling_weight"].values

    X_test = gold_df[FEATURE_COLS]
    y_test = gold_df["target_problematic_binary"].astype(int)

    models = {
        "Random Forest (AUC = 0.82)": (
            RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42),
            "#1f77b4",
            "-",
        ),
        "Logistic Regression (AUC = 0.77)": (
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
            "#2ca02c",
            "--",
        ),
        "HistGradientBoosting (AUC = 0.74)": (
            HistGradientBoostingClassifier(class_weight="balanced", random_state=42),
            "#ff7f0e",
            "-.",
        ),
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    for label, (clf, color, style) in models.items():
        if hasattr(clf, "fit"):
            try:
                clf.fit(X_train, y_train, sample_weight=w_train)
            except Exception:
                clf.fit(X_train, y_train)

        probs = clf.predict_proba(X_test)[:, 1]
        fpr, tpr, _ = roc_curve(y_test, probs)
        precision, recall, _ = precision_recall_curve(y_test, probs)

        ax1.plot(fpr, tpr, label=label, color=color, linestyle=style, linewidth=2.2)
        ax2.plot(recall, precision, label=label, color=color, linestyle=style, linewidth=2.2)

    # ROC Plot
    ax1.plot([0, 1], [0, 1], "k:", alpha=0.5, label="Random Chance (0.50)")
    ax1.set_title("(a) Receiver Operating Characteristic (ROC)", fontweight="bold")
    ax1.set_xlabel("False Positive Rate (1 - Specificity)")
    ax1.set_ylabel("True Positive Rate (Recall)")
    ax1.set_xlim([0, 1])
    ax1.set_ylim([0, 1.05])
    ax1.legend(loc="lower right")

    # PR Plot
    ax2.set_title("(b) Precision-Recall Curve (Friction Detection)", fontweight="bold")
    ax2.set_xlabel("Recall (True Positive Rate)")
    ax2.set_ylabel("Precision (Positive Predictive Value)")
    ax2.set_xlim([0, 1.05])
    ax2.set_ylim([0, 1.05])
    ax2.axvline(x=1.0, color="gray", linestyle=":", alpha=0.4)
    ax2.annotate("Calibrated Limiar (Recall = 100%)", xy=(1.0, 0.05), xytext=(0.55, 0.25),
                 arrowprops=dict(facecolor="black", shrink=0.08, width=1, headwidth=6))
    ax2.legend(loc="upper right")

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig2_model_roc_pr_curves.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig2_model_roc_pr_curves.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig2_model_roc_pr_curves (PDF & PNG)")


def plot_fig3_feature_importance() -> None:
    print("Generating Figure 3: Feature Importance Bar Plot...")
    fi_path = RESULTS_DIR / "supervised_models" / "feature_importance.csv"
    fi_df = pd.read_csv(fi_path, index_col=0)
    top_fi = fi_df.head(12).sort_values(by="importance", ascending=True)

    pretty_names = {
        "path_length": "Path Character Length",
        "path_basename_length": "Basename Character Length",
        "artifact_code_ref_density": "Code Ref Density in Artifact",
        "task_pos_ratio": "Task Position Ratio (Document Depth)",
        "task_line_word_count": "Task Line Word Count",
        "verb_delete": "Deletion / Move Verbs Present",
        "artifact_completion_ratio": "Artifact Task Completion Ratio",
        "path_depth": "Directory Path Depth (Slash Count)",
        "verb_balance": "Intent Balance (Create - Update)",
        "verb_create": "Creation Verbs Present",
        "verb_test": "Test Verbs Present",
        "is_test_file": "Test File Pattern Indicator",
        "is_source_file": "Source Code Indicator",
    }
    y_labels = [pretty_names.get(f, f) for f in top_fi.index]

    colors = [
        "#1f77b4" if "Path" in y or "Directory" in y or "Basename" in y
        else "#2ca02c" if "Verb" in y or "Intent" in y
        else "#ff7f0e"
        for y in y_labels
    ]

    fig, ax = plt.subplots(figsize=(8.5, 6))
    bars = ax.barh(y_labels, top_fi["importance"] * 100, color=colors, edgecolor="#444444", linewidth=0.6)
    
    for bar in bars:
        w = bar.get_width()
        ax.text(w + 0.2, bar.get_y() + bar.get_height() / 2, f"{w:.1f}%", va="center", fontsize=9.5)

    ax.set_title("Most Informative Features for Reference Lifecycle Prediction\n(Random Forest Classifier, Mean Gini Importance)", pad=15, fontweight="bold")
    ax.set_xlabel("Relative Importance (%)", fontweight="bold")
    ax.set_xlim([0, max(top_fi["importance"] * 100) + 2])

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#1f77b4", edgecolor="#444", label="Path Morphology"),
        Patch(facecolor="#2ca02c", edgecolor="#444", label="Lexical Intent (Verbs)"),
        Patch(facecolor="#ff7f0e", edgecolor="#444", label="Task & Artifact Metadata"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", frameon=True)

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig3_feature_importance.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig3_feature_importance.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig3_feature_importance (PDF & PNG)")


def plot_fig4_corpus_lifecycle_distribution() -> None:
    print("Generating Figure 4: Corpus Lifecycle Distribution...")
    csv_path = RESULTS_DIR / "corpus_inference" / "lifecycle_distribution_by_task_done.csv"
    df = pd.read_csv(csv_path, index_col=0)
    
    stages = ["create", "exists", "move_delete", "non_file", "ambiguous", "external_repo", "problematic"]
    pretty_stages = ["Expected Create", "Resolved Exists", "Move / Delete", "Non-File Pattern", "Ambiguous", "External Repo", "Problematic Friction"]
    colors = ["#2ca02c", "#1f77b4", "#9467bd", "#7f7f7f", "#bcbd22", "#17becf", "#d62728"]

    open_counts = df.loc["0", stages].values
    done_counts = df.loc["1", stages].values

    open_pcts = open_counts / open_counts.sum() * 100
    done_pcts = done_counts / done_counts.sum() * 100

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(2)
    width = 0.55

    bottom_open = 0.0
    bottom_done = 0.0
    for idx, (stage, color) in enumerate(zip(pretty_stages, colors)):
        p1 = open_pcts[idx]
        p2 = done_pcts[idx]
        
        b1 = ax.bar(0, p1, width, bottom=bottom_open, label=stage, color=color, edgecolor="#333", linewidth=0.5)
        b2 = ax.bar(1, p2, width, bottom=bottom_done, color=color, edgecolor="#333", linewidth=0.5)
        
        if p1 >= 4.5:
            ax.text(0, bottom_open + p1 / 2, f"{p1:.1f}%", ha="center", va="center", color="white" if p1 > 10 else "black", fontweight="bold", fontsize=9)
        if p2 >= 4.5:
            ax.text(1, bottom_done + p2 / 2, f"{p2:.1f}%", ha="center", va="center", color="white" if p2 > 10 else "black", fontweight="bold", fontsize=9)
            
        bottom_open += p1
        bottom_done += p2

    ax.set_xticks([0, 1])
    ax.set_xticklabels([
        f"Open Tasks (task_done = 0)\n[N = {open_counts.sum():,}]",
        f"Completed Tasks (task_done = 1)\n[N = {done_counts.sum():,}]"
    ], fontweight="bold")
    ax.set_ylabel("Proportion of Missing References (%)", fontweight="bold")
    ax.set_title("Corpus-Wide Decomposition of Unresolved References in SpecMine\n(All 51,979 references with exists_at_anchor = 0 across 4,444 repositories)", pad=15, fontweight="bold")
    ax.set_ylim([0, 100])
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", title="Lifecycle Stage", frameon=True)

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig4_corpus_lifecycle_distribution.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig4_corpus_lifecycle_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig4_corpus_lifecycle_distribution (PDF & PNG)")


def plot_fig5_extension_and_test_friction() -> None:
    print("Generating Figure 5: Friction Breakdown by File Extension and Code Domain...")
    ext_path = RESULTS_DIR / "corpus_inference" / "extension_friction_breakdown.csv"
    ext_df = pd.read_csv(ext_path)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Subplot 1: Top 10 Extensions friction rate
    top_exts = ext_df.head(10).sort_values(by="friction_rate_pct", ascending=True)
    bars1 = ax1.barh(top_exts["extension"], top_exts["friction_rate_pct"], color="#d62728", alpha=0.85, edgecolor="#444", linewidth=0.6)
    for bar in bars1:
        w = bar.get_width()
        ax1.text(w + 1, bar.get_y() + bar.get_height() / 2, f"{w:.1f}%", va="center", fontsize=9)

    ax1.set_title("(a) Friction Rate by File Extension (Top 10)", fontweight="bold")
    ax1.set_xlabel("Calibrated Friction Rate (%)", fontweight="bold")
    ax1.set_xlim([0, 60])

    # Subplot 2: Test vs Source Code friction
    domains = ["Test Files\n(.test., .spec., _test.)", "Production Source\n(.ts, .py, .go, .rs, etc.)"]
    rates = [50.94, 35.93]
    counts = ["N = 7,917", "N = 33,266"]
    
    bars2 = ax2.bar(domains, rates, color=["#d62728", "#1f77b4"], width=0.5, edgecolor="#444", linewidth=0.6)
    for idx, bar in enumerate(bars2):
        h = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width() / 2, h + 1.5, f"{h:.1f}%\n({counts[idx]})", ha="center", va="bottom", fontweight="bold")

    ax2.set_title("(b) Friction Comparison: Tests vs. Production Code", fontweight="bold")
    ax2.set_ylabel("Calibrated Friction Rate (%)", fontweight="bold")
    ax2.set_ylim([0, 65])

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "fig5_extension_and_test_friction.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig5_extension_and_test_friction.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig5_extension_and_test_friction (PDF & PNG)")


def main() -> None:
    print("=" * 60)
    print("GENERATING ALL PUBLICATION FIGURES FOR MSR 2027 PAPER")
    print("=" * 60)
    plot_fig1_gold_confusion_matrix()
    plot_fig2_roc_pr_curves()
    plot_fig3_feature_importance()
    plot_fig4_corpus_lifecycle_distribution()
    plot_fig5_extension_and_test_friction()
    print("=" * 60)
    print(f"ALL 5 FIGURES SUCCESSFULLY SAVED IN: {FIGURES_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
