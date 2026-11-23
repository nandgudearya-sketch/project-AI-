"""Report figures: ``python -m balancer figures`` (needs matplotlib).

Writes PNG charts plus a CSV of the numbers behind each chart to
``docs/figures/`` so the report can show both the picture and the table:

1. ablation_vs_lift      ablation value vs opening-hand lift, default game
2. planted_ablation      how each planted card change moves that card's value
3. seat_card_value       each card's value when owned by seat 1 vs seat 2
4. agent_ladder          strong agent's score in each skill-ladder pairing

Only this module needs matplotlib; the rest of the tool stays standard-library.
"""
from __future__ import annotations

import csv
import os

from .suite import ablation_detection, agent_ladder

BLUE, ORANGE = "#2a78d6", "#eb6834"          # categorical slots 1 and 2
INK, INK2, MUTED, SURFACE = "#0b0b0b", "#52514e", "#898781", "#fcfcfb"


def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:  # pragma: no cover
        raise SystemExit("Figures need matplotlib: pip install matplotlib") from e
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "text.color": INK,
        "xtick.color": INK2, "ytick.color": INK2, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.8,
        "axes.axisbelow": True, "legend.frameon": False,
    })
    return plt


def _pct(ax, axis="x"):
    from matplotlib.ticker import PercentFormatter
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(PercentFormatter(1.0, 0))


def _save(fig, out_dir, name, header, rows):
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f"{name}.png"), dpi=200)
    with open(os.path.join(out_dir, f"{name}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _paired_hbars(plt, labels, a, b, a_err, b_err, a_name, b_name, title, xlabel):
    fig, ax = plt.subplots(figsize=(7, 0.42 * len(labels) + 1.4))
    y = list(range(len(labels)))[::-1]
    h = 0.36
    kw = dict(height=h, edgecolor=SURFACE, linewidth=1)
    ax.barh([v + h / 2 for v in y], a, color=BLUE, label=a_name, xerr=a_err,
            error_kw=dict(ecolor=INK2, lw=1, capsize=2), **kw)
    ax.barh([v - h / 2 for v in y], b, color=ORANGE, label=b_name, xerr=b_err,
            error_kw=dict(ecolor=INK2, lw=1, capsize=2), **kw)
    ax.set_yticks(y, labels)
    ax.axvline(0, color=MUTED, lw=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(xlabel)
    ax.set_title(title, loc="left", fontsize=11, color=INK)
    _pct(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16 - 0.9 / (len(labels) + 3)),
              ncol=2)
    return fig, ax


def make_figures(out_dir="docs/figures", n_seeds=500, ladder_games=120, workers=None,
                 log=print):
    plt = _plt()
    os.makedirs(out_dir, exist_ok=True)

    log("Running ablation experiments...")
    abl = ablation_detection(n_seeds=n_seeds, workers=workers, log=None)
    base = abl["baseline"]

    # 1. Ablation vs opening-hand lift
    comp = abl["comparison"]
    fig, _ = _paired_hbars(
        plt, [r["card"] for r in comp], [r["ablation"] for r in comp],
        [r["lift"] for r in comp], [1.96 * c.se for c in base.cards], None,
        "Ablation value (vs ember)", "Opening-hand lift",
        "Card strength in the default game: two measures",
        "Change in win rate")
    _save(fig, out_dir, "ablation_vs_lift", ["card", "ablation_value", "opening_hand_lift"],
          [(r["card"], f"{r['ablation']:.4f}", f"{r['lift']:.4f}") for r in comp])
    plt.close(fig)

    # 2. Planted changes
    cases = abl["cases"]
    labels = [f"{c['card']}\n({c['preset']})" for c in cases]
    fig, ax = _paired_hbars(
        plt, labels, [c["before"] for c in cases], [c["after"] for c in cases],
        None, None, "Default game", "Planted preset",
        "Ablation detects each planted card change",
        "Card value vs ember (change in win rate)")
    _save(fig, out_dir, "planted_ablation",
          ["preset", "card", "value_default", "value_planted", "z", "rank", "detected"],
          [(c["preset"], c["card"], f"{c['before']:.4f}", f"{c['after']:.4f}",
            f"{c['z']:.2f}", c["rank"], c["detected"]) for c in cases])
    plt.close(fig)

    # 3. Per-seat card value
    cards = base.cards
    fig, _ = _paired_hbars(
        plt, [c.label for c in cards], [c.value_first for c in cards],
        [c.value_second for c in cards], [1.96 * c.se_first for c in cards],
        [1.96 * c.se_second for c in cards], "Owned by seat 1", "Owned by seat 2",
        "Card value by seat (default game, greedy self-play)",
        "Card value vs ember (change in win rate)")
    _save(fig, out_dir, "seat_card_value",
          ["card", "value_seat1", "se_seat1", "value_seat2", "se_seat2", "gap_z"],
          [(c.label, f"{c.value_first:.4f}", f"{c.se_first:.4f}",
            f"{c.value_second:.4f}", f"{c.se_second:.4f}", f"{c.seat_gap_z:.2f}")
           for c in cards])
    plt.close(fig)

    # 4. Agent ladder
    log("Running agent skill ladder...")
    rows = agent_ladder(n_games=ladder_games, workers=workers, log=None)
    names = [f"{r['strong']}\nvs {r['weak']}" for r in rows]
    scores = [r["score"] for r in rows]
    lo = [r["score"] - r["ci"][0] for r in rows]
    hi = [r["ci"][1] - r["score"] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(names, scores, color=BLUE, width=0.55, edgecolor=SURFACE,
           yerr=[lo, hi], error_kw=dict(ecolor=INK2, lw=1, capsize=3))
    ax.axhline(0.5, color=MUTED, lw=1, ls="--")
    ax.text(0.5, 0.51, "even\nmatch", color=MUTED, ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, 1)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Strong agent's score (95% CI)")
    ax.set_title("Skill increases with search budget", loc="left", fontsize=11, color=INK)
    _pct(ax, "y")
    _save(fig, out_dir, "agent_ladder", ["strong", "weak", "score", "ci_low", "ci_high"],
          [(r["strong"], r["weak"], f"{r['score']:.4f}", f"{r['ci'][0]:.4f}",
            f"{r['ci'][1]:.4f}") for r in rows])
    plt.close(fig)

    log(f"Saved 4 figures (PNG + CSV) to {out_dir}/")
    return out_dir


# Ordinal blue ramp (light -> dark = weaker -> stronger agent).
SKILL_RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]


def skill_figure(rep, out_dir="docs/figures", name="card_value_by_skill"):
    """Dot plot: one row per card, one dot per agent (darker = stronger), joined
    by a thin line so the change with skill is easy to see. Error bars are 95% CIs."""
    plt = _plt()
    os.makedirs(out_dir, exist_ok=True)
    agents = rep.agents
    colors = (SKILL_RAMP * 2)[-len(agents):] if len(agents) <= 4 else None
    if colors is None:
        raise ValueError("skill_figure supports up to 4 agents")
    cards = rep.order
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(cards) + 1.6))
    y = {c: len(cards) - 1 - i for i, c in enumerate(cards)}
    off = {a: (i - (len(agents) - 1) / 2) * 0.16 for i, a in enumerate(agents)}
    for c in cards:
        xs = [rep.values[c][a][0] for a in agents]
        ax.plot(xs, [y[c] + off[a] for a in agents], color="#c9c8c3", lw=1.5, zorder=1)
    for a, col in zip(agents, colors):
        xs = [rep.values[c][a][0] for c in cards]
        es = [1.96 * rep.values[c][a][1] for c in cards]
        ax.errorbar(xs, [y[c] + off[a] for c in cards], xerr=es, fmt="o", ms=7,
                    color=col, ecolor=col, elinewidth=1, capsize=0,
                    markeredgecolor=SURFACE, markeredgewidth=1.5, label=a, zorder=2)
    flagged = {s for _, s, _ in rep.issues}
    ax.set_yticks([y[c] for c in cards],
                  [f"{c}  *" if c in flagged else c for c in cards])
    ax.axvline(0, color=MUTED, lw=1)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"Card value vs {rep.reference} (change in win rate)")
    ax.set_title("Card value by player skill (weakest → strongest)", loc="left",
                 fontsize=11, color=INK)
    _pct(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=len(agents),
              handletextpad=0.3)
    if flagged:
        fig.text(0.01, 0.01, "* value changes significantly with skill", color=INK2,
                 fontsize=8.5)
    _save(fig, out_dir, name, ["card"] + [f"{a}_{k}" for a in agents for k in ("value", "se")],
          [[c] + [f"{x:.4f}" for a in agents for x in rep.values[c][a]] for c in cards])
    plt.close(fig)
    return os.path.join(out_dir, f"{name}.png")
