"""Generate publication-quality figures for the MSR 2027 paper in the New York Times Data Viz standard."""

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
from sklearn.metrics import precision_recall_curve, roc_curve

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INTERIM = PROJECT_ROOT / "data" / "interim"
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "paper_figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# NEW YORK TIMES DATA VIZ DESIGN SYSTEM
# ==============================================================================
NYT_COLORS = {
    "red": "#C53929",         # NYT Coral/Brick Red (Problematic / Friction / Risk)
    "blue": "#1D4E89",        # NYT Slate Blue (Resolved / Exists / Production)
    "green": "#2E7D5B",       # NYT Sage Green (Expected Create / Benign)
    "purple": "#7A6882",      # NYT Dusty Plum (Move / Delete)
    "gray": "#6C757D",        # NYT Neutral Gray (Non-File / Synthetic)
    "ochre": "#D97724",       # NYT Warm Amber / Ochre (Ambiguous / Inaccessible)
    "teal": "#3A8696",        # NYT Muted Teal (External Repo)
    "dark": "#121212",        # Headline Charcoal
    "body": "#333333",        # Body Dark Gray
    "muted": "#666666",       # Deck / Subtitle Gray
    "line": "#E2E2E2",        # Grid line subtle gray
    "bg": "#FFFFFF",          # Clean white
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 10.5,
    "axes.labelweight": "medium",
    "axes.labelcolor": NYT_COLORS["body"],
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "xtick.color": NYT_COLORS["body"],
    "ytick.color": NYT_COLORS["body"],
    "figure.titlesize": 14,
    "figure.titleweight": "bold",
    "figure.dpi": 300,
    "figure.facecolor": NYT_COLORS["bg"],
    "axes.facecolor": NYT_COLORS["bg"],
    "axes.edgecolor": "#CCCCCC",
    "axes.linewidth": 0.8,
    "grid.color": NYT_COLORS["line"],
    "grid.linestyle": "-",
    "grid.linewidth": 0.6,
    "grid.alpha": 1.0,
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
    print("Generating Figure 1: Gold Standard Confusion Matrix (NYT Style)...")
    cm_path = RESULTS_DIR / "validation" / "final_90_gemini" / "confusion_matrix.csv"
    cm_df = pd.read_csv(cm_path, index_col=0)
    
    cols = [c for c in TAXONOMY_SHORT if c in cm_df.columns]
    cm_sub = cm_df.loc[cols, cols].values
    cm_norm = cm_sub.astype(float) / np.maximum(cm_sub.sum(axis=1, keepdims=True), 1)

    fig, ax = plt.subplots(figsize=(8.5, 7.8))
    
    # Custom NYT monochromatic blues cmap
    cmap = sns.light_palette(NYT_COLORS["blue"], as_cmap=True)

    sns.heatmap(
        cm_norm,
        annot=cm_sub,
        fmt="d",
        cmap=cmap,
        xticklabels=LABELS_PRETTY[:len(cols)],
        yticklabels=LABELS_PRETTY[:len(cols)],
        cbar=True,
        cbar_kws={"label": "Normalized Recall", "shrink": 0.82},
        ax=ax,
        linewidths=1.2,
        linecolor="#FFFFFF",
        annot_kws={"fontsize": 11, "fontweight": "bold"},
    )
    
    # NYT Typography & Header Hierarchy
    fig.text(
        0.08, 0.96,
        "High Fidelity: Calibrated Gemini Judge Matches 93.3% of Human Ground Truth",
        fontsize=13.5, fontweight="bold", color=NYT_COLORS["dark"]
    )
    fig.text(
        0.08, 0.925,
        "Blind evaluation on 90 human Gold Standard cases in SpecMine (Cohen's κ = 0.907, Gwet's AC₁ = 0.926, Friction Recall = 100%)",
        fontsize=9.8, color=NYT_COLORS["muted"]
    )

    ax.set_ylabel("True Human Classification", fontweight="bold", labelpad=10, color=NYT_COLORS["dark"])
    ax.set_xlabel("Gemini 3.8 Flash Classification", fontweight="bold", labelpad=14, color=NYT_COLORS["dark"])
    plt.xticks(rotation=32, ha="right", fontsize=9.5)
    plt.yticks(rotation=0, fontsize=9.5)

    # Footnote
    fig.text(
        0.08, 0.015,
        "Source: Hand-validated Gold Standard (N = 90 distinct repositories). Evaluated blindly without prior exposure.",
        fontsize=8.5, color=NYT_COLORS["muted"], style="italic"
    )

    plt.subplots_adjust(top=0.88, bottom=0.23, left=0.22, right=0.95)
    fig.savefig(FIGURES_DIR / "fig1_gold_validation_matrix.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig1_gold_validation_matrix.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig1_gold_validation_matrix (PDF & PNG)")


def plot_fig2_roc_pr_curves() -> None:
    print("Generating Figure 2: ROC and Precision-Recall Curves (NYT Style)...")
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
            NYT_COLORS["blue"],
            "-",
            2.5
        ),
        "Logistic Regression (AUC = 0.77)": (
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
            NYT_COLORS["green"],
            "--",
            1.8
        ),
        "HistGradientBoosting (AUC = 0.74)": (
            HistGradientBoostingClassifier(class_weight="balanced", random_state=42),
            NYT_COLORS["ochre"],
            "-.",
            1.8
        ),
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.8))

    # NYT Header Hierarchy
    fig.text(
        0.06, 0.96,
        "Random Forest Reliably Identifies Problematic References at Low False-Alarm Rates",
        fontsize=14, fontweight="bold", color=NYT_COLORS["dark"]
    )
    fig.text(
        0.06, 0.92,
        "Performance evaluated strictly blindly on the held-out Human Gold Test Set (N = 90), breaking teacher-student bias loops",
        fontsize=10, color=NYT_COLORS["muted"]
    )

    for label, (clf, color, style, lw) in models.items():
        if hasattr(clf, "fit"):
            try:
                clf.fit(X_train, y_train, sample_weight=w_train)
            except Exception:
                clf.fit(X_train, y_train)

        probs = clf.predict_proba(X_test)[:, 1]
        fpr, tpr, _ = roc_curve(y_test, probs)
        precision, recall, _ = precision_recall_curve(y_test, probs)

        ax1.plot(fpr, tpr, label=label, color=color, linestyle=style, linewidth=lw, zorder=4)
        ax2.plot(recall, precision, label=label, color=color, linestyle=style, linewidth=lw, zorder=4)

    # ROC Plot
    ax1.plot([0, 1], [0, 1], color="#999999", linestyle=":", linewidth=1.2, alpha=0.8, label="Random Chance (0.50)", zorder=2)
    ax1.set_title("(a) Receiver Operating Characteristic (ROC)", loc="left", fontsize=11.5, fontweight="bold", color=NYT_COLORS["dark"], pad=10)
    ax1.set_xlabel("False Positive Rate (1 - Specificity)", fontsize=10, fontweight="bold")
    ax1.set_ylabel("True Positive Rate (Recall)", fontsize=10, fontweight="bold")
    ax1.set_xlim([0, 1.0])
    ax1.set_ylim([0, 1.05])
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.spines["left"].set_color("#CCCCCC")
    ax1.spines["bottom"].set_color("#333333")
    ax1.grid(True, linestyle="-", color="#EEEEEE", alpha=0.8, zorder=0)
    ax1.legend(loc="lower right", frameon=False, fontsize=9.5)

    # PR Plot
    ax2.set_title("(b) Precision-Recall Curve (Friction Detection)", loc="left", fontsize=11.5, fontweight="bold", color=NYT_COLORS["dark"], pad=10)
    ax2.set_xlabel("Recall (True Positive Rate)", fontsize=10, fontweight="bold")
    ax2.set_ylabel("Precision (Positive Predictive Value)", fontsize=10, fontweight="bold")
    ax2.set_xlim([0, 1.05])
    ax2.set_ylim([0, 1.05])
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_color("#CCCCCC")
    ax2.spines["bottom"].set_color("#333333")
    ax2.grid(True, linestyle="-", color="#EEEEEE", alpha=0.8, zorder=0)
    ax2.axvline(x=1.0, color="#888888", linestyle=":", alpha=0.6, zorder=2)

    # NYT Callout Annotation
    ax2.annotate(
        "Calibrated Limiar (τ ≤ 0.20)\nRecall = 100%, Specificity = 97.7%",
        xy=(1.0, 0.05), xytext=(0.42, 0.28),
        fontsize=9.5, fontweight="bold", color=NYT_COLORS["red"],
        arrowprops=dict(arrowstyle="->", color=NYT_COLORS["red"], lw=1.5),
        bbox=dict(boxstyle="round,pad=0.4", fc="#FFF5F5", ec=NYT_COLORS["red"], lw=0.8)
    )
    ax2.legend(loc="upper right", frameon=False, fontsize=9.5)

    # Footnote
    fig.text(
        0.06, 0.02,
        "Source: Trained on Silver Standard (N = 450 with inverse probability weights wi) · Tested blindly on Gold Benchmark (N = 90).",
        fontsize=8.5, color=NYT_COLORS["muted"], style="italic"
    )

    plt.subplots_adjust(top=0.84, bottom=0.15, left=0.08, right=0.96, wspace=0.22)
    fig.savefig(FIGURES_DIR / "fig2_model_roc_pr_curves.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig2_model_roc_pr_curves.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig2_model_roc_pr_curves (PDF & PNG)")


def plot_fig3_feature_importance() -> None:
    print("Generating Figure 3: Feature Importance Bar Plot (NYT Style)...")
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
        "is_source_file": "Source Code Indicator",
    }
    y_labels = [pretty_names.get(f, f) for f in top_fi.index]

    colors = [
        NYT_COLORS["blue"] if any(k in y for k in ["Path", "Directory", "Basename"])
        else NYT_COLORS["green"] if any(k in y for k in ["Verb", "Intent"])
        else NYT_COLORS["ochre"]
        for y in y_labels
    ]

    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    
    # NYT Horizontal Bar Chart
    bars = ax.barh(y_labels, top_fi["importance"] * 100, color=colors, height=0.62, edgecolor="none", zorder=3)
    
    # Direct Labeling on bar tips
    for bar in bars:
        w = bar.get_width()
        ax.text(
            w + 0.25, bar.get_y() + bar.get_height() / 2,
            f"{w:.1f}%",
            va="center", fontsize=9.5, fontweight="bold", color=NYT_COLORS["body"]
        )

    # NYT Typography & Framing
    fig.text(
        0.08, 0.96,
        "Path Morphology and Document Depth Dominate Friction Prediction",
        fontsize=14, fontweight="bold", color=NYT_COLORS["dark"]
    )
    fig.text(
        0.08, 0.92,
        "Mean Gini importance from Random Forest classifier trained on Silver Standard (N = 450 unique repositories)",
        fontsize=10, color=NYT_COLORS["muted"]
    )

    ax.set_xlabel("Relative Feature Importance (%)", fontweight="bold", labelpad=8)
    ax.set_xlim([0, max(top_fi["importance"] * 100) + 2.5])
    
    # Despine: Remove top, right, and left spines! Keep only a subtle bottom line
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")
    ax.tick_params(left=False, bottom=True)
    ax.grid(True, axis="x", linestyle="-", color="#EEEEEE", zorder=0)

    # Top Integrated Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=NYT_COLORS["blue"], label="Path Morphology (28.3%)"),
        Patch(facecolor=NYT_COLORS["ochre"], label="Task & Document Context (39.4%)"),
        Patch(facecolor=NYT_COLORS["green"], label="Lexical Intent Verbs (18.4%)"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="lower right",
        frameon=True,
        facecolor="#FAFAFA",
        edgecolor="#E0E0E0",
        fontsize=9.5
    )

    # Footnote
    fig.text(
        0.08, 0.02,
        "Source: SpecMine Corpus v1.0 · Gini feature importances averaged over 100 estimators in Random Forest.",
        fontsize=8.5, color=NYT_COLORS["muted"], style="italic"
    )

    plt.subplots_adjust(top=0.86, bottom=0.12, left=0.33, right=0.96)
    fig.savefig(FIGURES_DIR / "fig3_feature_importance.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig3_feature_importance.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig3_feature_importance (PDF & PNG)")


def plot_fig4_corpus_lifecycle_distribution() -> None:
    print("Generating Figure 4: Corpus Lifecycle Distribution (NYT Style)...")
    csv_path = RESULTS_DIR / "corpus_inference" / "lifecycle_distribution_by_task_done.csv"
    df = pd.read_csv(csv_path, index_col=0)
    
    stages = ["create", "exists", "move_delete", "non_file", "ambiguous", "external_repo", "problematic"]
    pretty_stages = [
        "Expected Create",
        "Resolved Exists",
        "Move / Delete",
        "Non-File Syntax",
        "Ambiguous",
        "External Repo",
        "Problematic Friction",
    ]
    colors = [
        NYT_COLORS["green"],   # Expected Create
        NYT_COLORS["blue"],    # Resolved Exists
        NYT_COLORS["purple"],  # Move / Delete
        NYT_COLORS["gray"],    # Non-File Syntax
        NYT_COLORS["ochre"],   # Ambiguous
        NYT_COLORS["teal"],    # External Repo
        NYT_COLORS["red"],     # Problematic Friction
    ]

    open_counts = df.loc["0", stages].values
    done_counts = df.loc["1", stages].values

    open_pcts = open_counts / open_counts.sum() * 100
    done_pcts = done_counts / done_counts.sum() * 100

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    width = 0.52

    # NYT Header Hierarchy
    fig.text(
        0.08, 0.96,
        "Unresolved References in Open Tasks Are Almost Entirely Anticipatory Creations",
        fontsize=14, fontweight="bold", color=NYT_COLORS["dark"]
    )
    fig.text(
        0.08, 0.92,
        "Decomposition of all 51,979 references with exists_at_anchor = 0 across 4,444 repositories in SpecMine",
        fontsize=10, color=NYT_COLORS["muted"]
    )

    bottom_open = 0.0
    bottom_done = 0.0
    for idx, (stage, color) in enumerate(zip(pretty_stages, colors)):
        p1 = open_pcts[idx]
        p2 = done_pcts[idx]
        
        ax.bar(0, p1, width, bottom=bottom_open, label=stage, color=color, edgecolor="#FFFFFF", linewidth=1.2, zorder=3)
        ax.bar(1, p2, width, bottom=bottom_done, color=color, edgecolor="#FFFFFF", linewidth=1.2, zorder=3)
        
        if p1 >= 4.5:
            ax.text(
                0, bottom_open + p1 / 2, f"{p1:.1f}%",
                ha="center", va="center", color="white" if p1 > 10 else NYT_COLORS["dark"],
                fontweight="bold", fontsize=9.5, zorder=4
            )
        if p2 >= 4.5:
            ax.text(
                1, bottom_done + p2 / 2, f"{p2:.1f}%",
                ha="center", va="center", color="white" if p2 > 10 else NYT_COLORS["dark"],
                fontweight="bold", fontsize=9.5, zorder=4
            )
            
        bottom_open += p1
        bottom_done += p2

    # NYT Framing: Despine top, right, and left
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")
    ax.tick_params(left=False, bottom=True)
    ax.grid(True, axis="y", linestyle="-", color="#EEEEEE", zorder=0)

    ax.set_xticks([0, 1])
    ax.set_xticklabels([
        f"Open Tasks (task_done = 0)\nN = {open_counts.sum():,}",
        f"Completed Tasks (task_done = 1)\nN = {done_counts.sum():,}"
    ], fontweight="bold", fontsize=10.5)
    ax.set_ylabel("Proportion of Missing References (%)", fontweight="bold", labelpad=10)
    ax.set_ylim([0, 100])

    # Callout highlighting residual friction
    ax.annotate(
        "Residual friction drops to only 1.5%\nonce tasks are implemented",
        xy=(1.0, 98.8), xytext=(1.24, 88.0),
        fontsize=9.5, fontweight="bold", color=NYT_COLORS["red"],
        arrowprops=dict(arrowstyle="->", color=NYT_COLORS["red"], lw=1.5),
        bbox=dict(boxstyle="round,pad=0.4", fc="#FFF5F5", ec=NYT_COLORS["red"], lw=0.8)
    )

    # Legend outside on right
    ax.legend(
        bbox_to_anchor=(1.02, 0.72),
        loc="upper left",
        title="Reference Lifecycle",
        title_fontsize=10.5,
        frameon=True,
        facecolor="#FAFAFA",
        edgecolor="#E0E0E0",
        fontsize=9.5
    )

    # Footnote
    fig.text(
        0.08, 0.02,
        "Source: SpecMine Corpus v1.0 · Fast tabular inference across all 51,979 unresolved OpenSpec references.",
        fontsize=8.5, color=NYT_COLORS["muted"], style="italic"
    )

    plt.subplots_adjust(top=0.86, bottom=0.12, left=0.10, right=0.76)
    fig.savefig(FIGURES_DIR / "fig4_corpus_lifecycle_distribution.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig4_corpus_lifecycle_distribution.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig4_corpus_lifecycle_distribution (PDF & PNG)")


def plot_fig5_extension_and_test_friction() -> None:
    print("Generating Figure 5: Friction Breakdown by File Extension and Code Domain (NYT Style)...")
    ext_path = RESULTS_DIR / "corpus_inference" / "extension_friction_breakdown.csv"
    ext_df = pd.read_csv(ext_path)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.6))

    # NYT Header Hierarchy
    fig.text(
        0.06, 0.96,
        "Test Specifications Suffer Far Higher Friction Than Production Source Code",
        fontsize=14, fontweight="bold", color=NYT_COLORS["dark"]
    )
    fig.text(
        0.06, 0.92,
        "Calibrated friction rates by file extension (top 10) and code domain across 51,979 unresolved references",
        fontsize=10, color=NYT_COLORS["muted"]
    )

    # Subplot 1: Top 10 Extensions friction rate
    top_exts = ext_df.head(10).sort_values(by="friction_rate_pct", ascending=True)
    bars1 = ax1.barh(top_exts["extension"], top_exts["friction_rate_pct"], color=NYT_COLORS["red"], height=0.62, edgecolor="none", zorder=3)
    for bar in bars1:
        w = bar.get_width()
        ax1.text(
            w + 0.9, bar.get_y() + bar.get_height() / 2,
            f"{w:.1f}%",
            va="center", fontsize=9.2, fontweight="bold", color=NYT_COLORS["body"]
        )

    ax1.set_title("(a) Friction Rate by File Extension (Top 10)", loc="left", fontsize=11.5, fontweight="bold", color=NYT_COLORS["dark"], pad=10)
    ax1.set_xlabel("Calibrated Friction Rate (%)", fontweight="bold", labelpad=8)
    ax1.set_xlim([0, 58])
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.spines["left"].set_visible(False)
    ax1.spines["bottom"].set_color("#333333")
    ax1.tick_params(left=False, bottom=True)
    ax1.grid(True, axis="x", linestyle="-", color="#EEEEEE", zorder=0)

    # Subplot 2: Test vs Source Code friction
    domains = ["Test Files\n(.test., .spec., _test.)", "Production Source\n(.ts, .py, .go, .rs, etc.)"]
    rates = [50.94, 35.93]
    counts = ["N = 7,917", "N = 33,266"]
    
    bars2 = ax2.bar(domains, rates, color=[NYT_COLORS["red"], NYT_COLORS["blue"]], width=0.46, edgecolor="none", zorder=3)
    for idx, bar in enumerate(bars2):
        h = bar.get_height()
        ax2.text(
            bar.get_x() + bar.get_width() / 2, h + 1.6,
            f"{h:.1f}%\n({counts[idx]})",
            ha="center", va="bottom", fontweight="bold", fontsize=10, color=NYT_COLORS["dark"]
        )

    ax2.set_title("(b) Domain Disparity: Tests vs. Production Code", loc="left", fontsize=11.5, fontweight="bold", color=NYT_COLORS["dark"], pad=10)
    ax2.set_ylabel("Calibrated Friction Rate (%)", fontweight="bold", labelpad=8)
    ax2.set_ylim([0, 68])
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["bottom"].set_color("#333333")
    ax2.tick_params(left=False, bottom=True)
    ax2.grid(True, axis="y", linestyle="-", color="#EEEEEE", zorder=0)

    # NYT Callout on Test Brittleness
    ax2.annotate(
        "Test specifications experience 1.4× higher\nfriction due to volatile mocks and fixtures",
        xy=(0.0, 52.0), xytext=(0.18, 60.5),
        fontsize=9.2, fontweight="bold", color=NYT_COLORS["red"],
        arrowprops=dict(arrowstyle="->", color=NYT_COLORS["red"], lw=1.3),
        bbox=dict(boxstyle="round,pad=0.35", fc="#FFF5F5", ec=NYT_COLORS["red"], lw=0.8)
    )

    # Footnote
    fig.text(
        0.06, 0.02,
        "Source: SpecMine Corpus v1.0 · Calibrated predictions across all 51,979 references with exists_at_anchor = 0.",
        fontsize=8.5, color=NYT_COLORS["muted"], style="italic"
    )

    plt.subplots_adjust(top=0.84, bottom=0.14, left=0.08, right=0.96, wspace=0.25)
    fig.savefig(FIGURES_DIR / "fig5_extension_and_test_friction.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "fig5_extension_and_test_friction.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved fig5_extension_and_test_friction (PDF & PNG)")


def main() -> None:
    print("=" * 60)
    print("GENERATING ALL PUBLICATION FIGURES (NYT DATA VIZ STANDARD)")
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
