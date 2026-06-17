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

## With LangSmith Tracing

```bash
export LANGCHAIN_TRACING_V2=true; export LANGCHAIN_API_KEY="<key>"; export LANGCHAIN_PROJECT="dbfox-agent-e2e"; python -m pytest engine/ -q 2>&1
```

## With Backend Restart

```bash
cd "D:/Project/DBFox" && python .agent_eval/run_agent_eval.py --config .agent_eval/eval_config.yaml -q 2>&1 | tail -2 && python .agent_eval/start_eval_backend.py &
```

## Notes

- Backend must be running for eval to work. Use `start_eval_backend.py` to start it.
- Eval results are stored in `.agent_eval/results/`.
- The eval framework tests the full agent pipeline: db.observe → db.search → db.inspect → db.preview → db.query → db.remember.
