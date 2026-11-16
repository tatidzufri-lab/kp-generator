# На macOS WeasyPrint находит Pango/GObject из Homebrew только если путь
# к библиотекам задан до запуска процесса. Через export не работает:
# SIP вычищает DYLD_* при запуске /bin/sh, поэтому переменная ставится
# прямо перед python в каждой команде.
ifeq ($(shell uname),Darwin)
LIBENV := DYLD_FALLBACK_LIBRARY_PATH=$(shell brew --prefix 2>/dev/null || echo /opt/homebrew)/lib
endif

PY := $(LIBENV) .venv/bin/python

.PHONY: install run test check

install:
	python3.11 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env

run:
	$(PY) -m flask --app app run --debug --port 5050

test:
	$(PY) -m pytest -q

check:
	$(PY) -c "import weasyprint, flask, openai, pydantic, yaml, dotenv, jinja2; print('ok: weasyprint', weasyprint.__version__, '| openai', openai.__version__)"
