# Automated Playtesting and Balance Tuning

![tests](https://github.com/OWNER/game-balancer/actions/workflows/tests.yml/badge.svg)

**Team:** Karan Manish Shah, Nidhi Nimmagadda, Arya Atul Nandgude

Foundations of AI project (Khoury College, Northeastern). The tool plays a game
thousands of times with AI agents of different skill levels, reports balance
problems, searches for dominant strategies, and proposes parameter changes that
it then verifies by further simulation.

Pure Python 3.10+, standard library only. No installation needed.

```bash
git clone https://github.com/OWNER/game-balancer.git
cd game-balancer
pip install -e .                          # optional: adds a `balancer` command
python -m unittest discover tests         # 15 tests, ~2 s
python -m balancer list                   # games, presets, tunable parameters
python -m balancer simulate --preset planted_card
python -m balancer evaluate               # the full evaluation (~3 min on 1 core)
```

## Project layout

```
balancer/
  core/game.py            The abstract Game interface. Everything else only uses this.
  games/
    ember.py              Ember Duel: our original card game (main test case + planted imbalances)
    nim.py                Subtraction Nim: second game proving the engine is general
    __init__.py           Game registry
  agents/
    simple.py             random, greedy (turn planner), weighted (strategy), human
    mcts.py               Single-observer Information Set MCTS (handles hidden cards)
    __init__.py           make_agent("mcts:200") etc.
  sim/harness.py          Parallel simulation, seat swapping, seeded records
  analysis/balance.py     Balance report: seat advantage, card strength, dead cards,
                          game length, skill-vs-luck; Wilson confidence intervals
  search/strategy.py      Dominant-strategy search: card-focus probe + genetic algorithm
  tune/tuner.py           Hill-climbing tuner with common random numbers and held-out verification
  evaluation/suite.py     The proposal's three evaluation claims, as runnable experiments
  __main__.py             Command-line interface
tests/test_balancer.py
```

## How the pieces fit

1. **Game interface** (`core/game.py`). A game provides `initial_state(seed)`,
   `legal_actions`, `step` (in place), `clone`, `is_terminal`, `winner`, and
   optionally `determinize` (re-deal hidden cards), `heuristic`, and analytics
   hooks (`action_label`, `opening_labels`). All tunable numbers live in a flat
   `params` dict, so the tuner never needs game-specific code. All randomness is
   fixed by the seed when the state is created, so `step` is deterministic and
   every game is reproducible.
2. **Agents.** `random`; `greedy`, which plans its whole turn against the game
   heuristic; `mcts:N`, ISMCTS with N iterations per move (skill scales with
   N); `weighted:...`, a greedy planner biased toward or away from particular
   cards (the strategy space the search explores); and `human`.
3. **Harness.** Games run in a duplicate format: games 2k and 2k+1 use the same
   seed with seats swapped. This cancels deal luck when comparing agents and
   gives common random numbers for tuning.
4. **Analyzer.** Every rate comes with a 95% Wilson interval, and issues are
   flagged only when the interval clears a practical-significance margin.
5. **Search and tuning** reuse the harness and analyzer.

## Ember Duel rules

Each player has a 20-card deck (2 copies of 10 cards). Each turn you gain
energy equal to your turn number (max 8), score your growth, draw a card, then
play any affordable cards. First to 40 points wins; after 40 total turns the
higher score wins. The second player starts with 4 points and 1 extra card as
compensation. Cards score points, draw cards, give energy, steal points, or
add growth (points every turn). Every number is a parameter: `python -m balancer list`.

## Commands

```bash
# Balance report (add --luck for a skill-vs-luck check, --json out.json to save)
python -m balancer simulate --agents mcts:100 greedy --games 500
python -m balancer simulate --set flare.cost=2 target_points=35

# Dominant-strategy search
python -m balancer probe  --preset planted_engine          # favour-one-card strategies vs greedy
python -m balancer search --opponents greedy mcts:50       # genetic algorithm

# Propose and verify fixes
python -m balancer tune --preset planted_card --params flare.cost flare.points

# Play against an agent (for the "agents play reasonably vs humans" evaluation)
python -m balancer play --opponent mcts:200
```

Agent specs: `random`, `greedy`, `mcts:N`, `weighted:spark=0.5;siphon=-1`, `human`.

## Measuring card strength: why opening-hand lift

The obvious metric, win rate when a card is *played*, is badly confounded. For
example, inferno costs 7, so only players who survive to turn 7 can play it.
In one run it showed a 61.5% "win when played" rate while actually being
slightly *negative* to start with. The analyzer instead compares players who
had a card in their **opening hand** with those who did not. The shuffle
decides that, so the comparison is a randomized experiment and the lift is a
causal estimate of how much the card helps. The played-win-rate column is
still shown, but only as descriptive data.

## Evaluation results (from `python -m balancer evaluate`)

**1. Planted imbalances** (2,000 greedy self-play games each): 6/6 pass.

| Preset | Planted change | Expected flag | Result |
|---|---|---|---|
| default | none (control) | nothing | PASS, no flags |
| planted_seat | second player loses compensation | seat advantage (first) | PASS |
| planted_card | flare cost 3→1, points 4→6 | flare dominant | PASS |
| planted_engine | hearth cost 4→2 | hearth dominant | PASS |
| planted_dud | inferno cost 7→10 | inferno dead | PASS |
| planted_long | target 40→200 | games time out | PASS |

The dud and long presets also produce secondary findings (a second-player
advantage, growth becoming dominant). These are real consequences of the
change, not false positives: in a long game, a points-per-turn engine really
does take over.

**2. Agents play reasonably.**

| Match | Strong agent's score | 95% CI |
|---|---|---|
| mcts:25 vs random | 98.3% | 94.1–99.5% |
| mcts:100 vs mcts:25 | 65.0% | 56.1–72.9% |
| mcts:400 vs mcts:100 | 53.3% | 44.4–62.0% |
| mcts:400 vs greedy | 63.3% | 54.4–71.4% |

Skill increases with search budget, with diminishing returns past about 100
iterations (worth discussing in the report). In Nim, strong self-play recovers
the theoretical result: the first player wins 100% at pile 13 and 0% at pile 12
(a multiple of 4). The human-play side of this claim still needs your own
playtest sessions via `python -m balancer play`.

**3. Before/after tuning.** Starting from planted_seat (seat 1 wins 79.9%), the
tuner proposed `p2_start_points 0→3, p2_extra_cards 0→3`. On 3,000 fresh-seed
games, seat 1's score dropped to 47.2% (CI 45.4–49.0%) and flagged issues went
from 1 to 0. A different run proposed `0→3, 0→2` and reached 51.9%. Results
vary slightly because the tuner trains on 600 games; the held-out check is what
makes the claim trustworthy. On planted_card it proposed `flare.points 6→3`,
reducing flare's lift from 10.2% to 6.7%.

## Design decisions worth explaining in your report

- **Noise is the central problem.** Simulation results are random, so
  every comparison uses fixed seeds (common random numbers), duplicate seat
  swapping, confidence intervals, and a final check on held-out seeds. The
  tuner reports "NOT VERIFIED" if an improvement doesn't survive fresh seeds.
- **Balance depends on skill.** A card can be strong for experts and useless
  for beginners. Run `simulate` with several agent pairs and report results
  per skill level. Always use the same agent in both seats when measuring
  seat advantage.
- **Strategies are defined relative to greedy.** Weighted agents are greedy
  plus per-card preferences, so all-zero weights equals greedy and 50% is the
  fair baseline. A strategy that beats greedy has found a card the heuristic
  misprices.
- **MCTS tuning.** Long random rollouts in a card game are mostly noise. Ember
  uses 6-move rollouts with an informed policy, then the heuristic
  (`rollout_depth`, `mcts_c` on the game class). Nim has no heuristic, so it
  rolls out to the end.

## Adding a second game

1. Create `balancer/games/yourgame.py` and subclass `Game`. Set `name`,
   `DEFAULT_PARAMS`, `PARAM_SPACE` (integer bounds for tunables) and `PRESETS`,
   and implement the abstract methods. See `nim.py` for a minimal example and
   `ember.py` for hidden information.
2. Register it in `balancer/games/__init__.py`.
3. For hidden information, implement `determinize`. For card or action
   statistics, implement `all_action_labels`, `action_label` and
   `opening_labels`. For better MCTS, provide `heuristic` and set
   `rollout_depth`.

Everything else (agents, reports, search, tuning, CLI) then works unchanged.

## Limitations and next steps

- Opening-hand lift measures early-game impact; late-game cards can look weaker
  than they are. A "drawn by turn k" variant or an ablation (replace a card
  with a vanilla one and re-simulate) would be stronger.
- MCTS beats greedy only moderately in this simple race game. Better heuristics,
  more iterations, or ISMCTS with opponent modelling are natural extensions.
- The tuner is (1+λ) hill climbing. CMA-ES or a GA over parameters, or
  Bayesian optimization, would scale better to many parameters.
- Per-card lifts are pooled over both seats; splitting by seat can reveal cards
  that are only strong going first.

## Suggested team split

- **Agents** (`agents/`): MCTS improvements, human playtest sessions.
- **Analysis** (`analysis/`, `evaluation/`): metrics, planted cases, report figures.
- **Search and tuning** (`search/`, `tune/`): GA/probe, tuner, and verification experiments.
