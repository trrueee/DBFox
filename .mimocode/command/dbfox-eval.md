---
description: Run DBFox agent evaluation suite with optional backend restart
---

# Agent Eval Runner

Run the DBFox agent evaluation framework.

## Usage

```
/eval [config_name] [--restart-backend]
```

- `config_name`: Eval config file name (default: `eval_config.yaml` in `.agent_eval/`)
- `--restart-backend`: Also restart the Python backend after eval completes

## Default Command

```bash
cd "D:/Project/DBFox" && python .agent_eval/run_agent_eval.py --config .agent_eval/eval_config.yaml 2>&1
```

## Optional LangSmith Integration

LangSmith credentials are never supplied through shell or dotenv variables.
Any caller that enables the optional adapter must pass an opaque
`CredentialVault` reference to `LangSmithAdapter` at runtime.

## With Backend Restart

```bash
cd "D:/Project/DBFox" && python .agent_eval/run_agent_eval.py --config .agent_eval/eval_config.yaml -q 2>&1 | tail -2 && python .agent_eval/start_eval_backend.py &
```

## Notes

- Backend must be running for eval to work. Use `start_eval_backend.py` to start it.
- Eval results are stored in `.agent_eval/results/`.
- The eval framework tests the full agent pipeline: db.observe → db.search → db.inspect → db.preview → db.query → db.remember.
