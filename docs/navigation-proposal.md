# README navigation proposal

A proposed navigation section for the root `README.md`, to go after the opening summary and before "Principles". Paste the block below as it is: links are relative to the repository root. Rows that point at planned documents should be added when those documents land.

````markdown
## Start here

| I want to... | Go to |
|---|---|
| Understand the design and who owns what | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Find any document | [docs/README.md](docs/README.md) |
| See which model is tested and why | [docs/model-choice.md](docs/model-choice.md) |
| Read the practices behind the agent plumbing | [docs/best-practices.md](docs/best-practices.md) |
| Inspect a recorded run | [runs/](runs/) |
| Look up a behaviour id | [behaviour/taxonomy.yaml](behaviour/taxonomy.yaml) |
| Report an agent behaviour I observed | [Behaviour report](https://github.com/hexrift/agent-black-box/issues/new?template=behaviour_report.yml) |
| Propose a new task | [Task proposal](https://github.com/hexrift/agent-black-box/issues/new?template=task_proposal.yml) |
| Contribute code or a task | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Report a leaked secret or vulnerability | [SECURITY.md](SECURITY.md) |

### Map

```text
agent-black-box/
├── tasks/            challenging tasks: prompt, fixture, hidden grader, notes
├── behaviour/        behaviour taxonomy (failure and success modes)
├── src/blackbox/     harness: runs tasks, records, redacts, grades
├── runs/             recorded runs (redacted) and runs/index.jsonl
├── ledger/           every agent, builder and subject, in agents.jsonl
├── plumbing/         agent plumbing used by the plumbed variant
├── docs/             research, model choice, ledger format, decisions (adr/)
├── video/            replay video built from run data
├── scripts/          secret scan, file validation, label sync
└── Makefile          every common command: run make help
```

### Three commands

```sh
make setup                                   # install into .venv
make test                                    # offline tests, free
make run-task TASK=<task-id> VARIANT=bare    # one real run, spends money
```
````

## Notes for the coordinator

- The table lists intent first, so a newcomer scans for what they want to do rather than for a file name.
- The map shows only top-level folders and fits on one screen. Update it if a module is added in ARCHITECTURE.md.
- `make run-task` depends on the harness CLI (`python -m blackbox run --task <id> --variant <v>`); adjust the Makefile if the harness exposes a different entry point.
