.PHONY: clean install test format validate check-venv integ

VENV_PATH := $(PWD)/.venv
VENV_BIN := $(VENV_PATH)/bin
PYTHON := $(VENV_BIN)/python
PIP := $(VENV_BIN)/pip

# Helper function to run commands in venv
define in_venv
	. "$(VENV_PATH)/bin/activate" && $1
endef

clean:
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -f .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf $(VENV_PATH)
	rm -rf *.egg-info

install:
	python -m venv $(VENV_PATH) --clear --upgrade-deps
	$(call in_venv, \
		$(PIP) install -e . && \
		$(PIP) install -e ".[dev]" \
	)
	$(VENV_BIN)/pip-compile --output-file=src/requirements.txt pyproject.toml

test:
	$(call in_venv, PYTHONPATH=src $(VENV_BIN)/coverage run -m pytest tests -s)
	$(call in_venv, $(VENV_BIN)/coverage report)

format:
	$(call in_venv, $(VENV_BIN)/black src tests)
	$(call in_venv, $(VENV_BIN)/isort src tests)
	$(call in_venv, $(VENV_BIN)/ruff check src --fix)

validate:
	$(call in_venv, $(VENV_BIN)/ruff check src --fix)
	$(call in_venv, PYTHONPATH=src $(VENV_BIN)/pylint --rcfile=.pylintrc src)
	$(call in_venv, $(VENV_BIN)/mypy --config-file=mypy.ini src)

check-venv:
	@test -d $(VENV_PATH) || (echo "Virtual environment not found. Please run 'make install' first." && exit 1)

test integ format validate: check-venv
