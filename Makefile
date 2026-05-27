.PHONY: test smoke pycheck runner-test

PYTHON ?= uv run python

pycheck:
	$(PYTHON) -m py_compile agent.py evaluator.py autoresearch_runner.py

runner-test:
	$(PYTHON) -m unittest test_autoresearch_runner.py test_agent.py test_evaluator.py

smoke:
	$(PYTHON) agent.py --instruction 'For the catalogue count report, how many products are Wall Paint? answer pattern: "<total: NUMBER>"' --json

test: pycheck runner-test smoke
