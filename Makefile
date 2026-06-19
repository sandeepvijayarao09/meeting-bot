# Meeting Bot — development tasks. `make check` runs everything CI would.

.PHONY: check lint type test swift-build swift-lint ext-check ext-test app models clean

check: lint type test swift-build swift-lint ext-check ext-test
	@echo "\n✓ all checks passed"

lint:
	uv run ruff check meetingbot tests scripts
	uv run ruff format --check meetingbot tests scripts

type:
	uv run mypy

test:
	uv run pytest

swift-build:
	cd mac && swift build -c release

swift-lint:
	cd mac && swift format lint --recursive Sources

ext-check:
	cd chrome-extension && npm install --no-fund --no-audit --silent && npx tsc --noEmit

# Unit-test the extension's JS (audio encoder) with Node's built-in test runner.
ext-test:
	cd chrome-extension && node --test test/*.test.mjs

# Build the distributable MeetingBot.app bundle.
app:
	bash scripts/build-app.sh

# Benchmark all Whisper model variants (downloads models on first run).
models:
	uv run python scripts/model_matrix.py

clean:
	rm -rf mac/.build chrome-extension/node_modules .venv dist/MeetingBot.app
