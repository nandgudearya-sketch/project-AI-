# Contributing

## Workflow
1. Create a branch per feature: `git checkout -b agents/better-rollouts`
2. Run the tests before pushing: `python -m unittest discover tests`
3. Open a pull request and ask a teammate to review it.

## Ownership
- `balancer/agents/` — agents and MCTS improvements, human playtests
- `balancer/analysis/`, `balancer/evaluation/` — metrics, planted cases, figures
- `balancer/search/`, `balancer/tune/` — strategy search and tuning

## Adding a game
See "Adding a second game" in the README.
