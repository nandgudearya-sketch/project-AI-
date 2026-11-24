"""Run the same balance checks on every game and compare them side by side:
``python -m balancer compare``.

The point of having several games is to show the tool is general: the same
agents, harness and analyzer work on a hidden-information card game, a solved
perfect-information game and a board game, with no game-specific analysis code. For each game we report

* first-player score in self-play (seat advantage) with its 95% CI,
* median game length,
* skill vs luck: how often a search agent beats a random one,
* issues flagged on the default rules (ideally none), and
* whether the analyzer catches that game's planted imbalance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..analysis.balance import analyze, skill_gap
from ..games import GAMES
from ..sim.harness import Simulator

# game -> (what it is, what it tests, planted preset, expected issue (kind, subject))
GAME_INFO = {
    "ember": ("card game, hidden hands", "card strength",
              "planted_card", ("dominant", "flare")),
    "nim":   ("perfect information, solved", "known theoretical answer",
              "pile 12", ("seat", "second")),
    "grid":  ("perfect-information board", "first-move advantage",
              "planted_seat", ("seat", "first")),
}
# Nim's known answer only appears under (near-)perfect play, so it gets a much
# stronger self-play agent and small piles where that agent plays perfectly
# (as in the evaluation suite): pile 13 is a first-player win in theory, pile 12
# (a multiple of 4) a second-player win. On the default pile of 21 even mcts:1000
# makes mistakes, so the measured answer there would not be trustworthy.
GAME_AGENT = {"nim": "mcts:1000"}
GAME_PARAMS = {"nim": ({"pile": 13, "max_take": 3}, {"pile": 12, "max_take": 3})}
GAME_NOTES = {"nim": "piles 13 and 12 are used; theory says pile 13 is a first-player "
                     "win, so seat:first is the correct answer there"}


@dataclass
class GameRow:
    game: str
    kind: str
    tests: str
    seat1: float
    seat1_ci: tuple
    length_p50: float
    skill: float
    skill_ci: tuple
    default_issues: list = field(default_factory=list)
    planted: str = ""
    expected: tuple = ()
    detected: bool = False
    planted_issues: list = field(default_factory=list)
    agent: str = ""
    note: str = ""


def _issues(rep, luck):
    out = [(i.kind, i.subject) for i in rep.issues]
    if luck and luck["issue"]:
        out.append((luck["issue"].kind, luck["issue"].subject))
    return out


def compare_games(games=None, agent="mcts:50", strong="mcts:100", n_games=600,
                  skill_games=200, workers=None, log=print) -> list[GameRow]:
    rows = []
    with Simulator(workers) as sim:
        for name in games or list(GAME_INFO):
            cls = GAMES[name]
            kind, tests, preset, expected = GAME_INFO[name]
            labels = cls().all_action_labels()
            a = GAME_AGENT.get(name, agent)
            if log:
                log(f"  {name}: default rules ...")
            if name in GAME_PARAMS:
                base, pp = GAME_PARAMS[name]
            else:
                base, pp = cls.preset_params(), cls.preset_params(preset)
            rep = analyze(sim.match(name, base, [a, a], n_games, 101), labels)
            luck = skill_gap(name, base, strong, "random", skill_games, 202, sim=sim)
            if log:
                log(f"  {name}: planted '{preset}' ...")
            prep = analyze(sim.match(name, pp, [a, a], n_games, 303), labels)
            pluck = skill_gap(name, pp, strong, "random", skill_games, 404, sim=sim)
            found = _issues(prep, pluck)
            rows.append(GameRow(
                name, kind, tests, rep.seat0_score, rep.seat0_ci, rep.length_p50,
                luck["score"], luck["ci"], _issues(rep, luck), preset, expected,
                tuple(expected) in found, found, a, GAME_NOTES.get(name, "")))
    return rows


def format_compare(rows, agent="mcts:50", strong="mcts:100") -> str:
    out = [f"=== Same checks on every game ({agent} self-play; skill = {strong} vs random) ===",
           "",
           f"  {'game':<7}{'type':<32}{'seat 1':>8}{'95% CI':>15}{'median':>8}"
           f"{'skill':>8}  default issues",
           ]
    notes = []
    for r in rows:
        ci = f"{r.seat1_ci[0]:.0%}-{r.seat1_ci[1]:.0%}"
        iss = ", ".join(f"{k}:{s}" for k, s in r.default_issues) or "none"
        out.append(f"  {r.game:<7}{r.kind:<32}{r.seat1:>8.1%}{ci:>15}{r.length_p50:>8.0f}"
                   f"{r.skill:>8.1%}  {iss}")
        if r.agent != agent:
            notes.append(f"  {r.game}: self-play uses {r.agent}.")
        if r.note:
            notes.append(f"  {r.game}: {r.note}.")
    out += notes
    out += ["", "  Planted imbalance detection",
            f"  {'game':<7}{'tests':<26}{'planted preset':<20}{'expected':<18}result"]
    for r in rows:
        exp = f"{r.expected[0]}:{r.expected[1]}"
        out.append(f"  {r.game:<7}{r.tests:<26}{r.planted:<20}{exp:<18}"
                   f"{'PASS' if r.detected else 'FAIL'}")
    passed = sum(r.detected for r in rows)
    out += ["", f"  {passed}/{len(rows)} planted imbalances detected."]
    return "\n".join(out)


def compare_figure(rows, out_dir="docs/figures", name="game_comparison"):
    """Two side-by-side panels: seat-1 score (with CI) and skill score per game."""
    import os
    from .figures import BLUE, INK, INK2, MUTED, SURFACE, _pct, _plt, _save
    plt = _plt()
    os.makedirs(out_dir, exist_ok=True)
    titles = {"ember": "Ember Duel", "nim": "Nim (pile 13)", "grid": "Claim"}
    names = [titles.get(r.game, r.game) for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8, 3.6), sharey=False)
    for ax, vals, cis, title, ref, ref_label in (
            (a1, [r.seat1 for r in rows], [r.seat1_ci for r in rows],
             "First player's score (fair = 50%)", 0.5, "fair"),
            (a2, [r.skill for r in rows], [r.skill_ci for r in rows],
             "Search agent vs random (skill)", 0.5, "coin flip")):
        lo = [v - c[0] for v, c in zip(vals, cis)]
        hi = [c[1] - v for v, c in zip(vals, cis)]
        ax.bar(names, vals, color=BLUE, width=0.55, edgecolor=SURFACE,
               yerr=[lo, hi], error_kw=dict(ecolor=INK2, lw=1, capsize=3))
        ax.axhline(ref, color=MUTED, lw=1, ls="--")
        ax.set_ylim(0, 1)
        ax.grid(axis="x", visible=False)
        ax.set_title(title, loc="left", fontsize=10.5, color=INK)
        _pct(ax, "y")
    fig.suptitle("Three games, same analyzer (default rules, 95% CIs)", x=0.01, ha="left",
                 fontsize=11.5, color=INK)
    _save(fig, out_dir, name,
          ["game", "type", "seat1", "seat1_lo", "seat1_hi", "median_length",
           "skill", "skill_lo", "skill_hi", "default_issues", "planted", "detected"],
          [(r.game, r.kind, f"{r.seat1:.4f}", f"{r.seat1_ci[0]:.4f}", f"{r.seat1_ci[1]:.4f}",
            r.length_p50, f"{r.skill:.4f}", f"{r.skill_ci[0]:.4f}", f"{r.skill_ci[1]:.4f}",
            ";".join(f"{k}:{s}" for k, s in r.default_issues), r.planted, r.detected)
           for r in rows])
    plt.close(fig)
    return os.path.join(out_dir, f"{name}.png")


def rows_to_dicts(rows):
    return [asdict(r) for r in rows]
