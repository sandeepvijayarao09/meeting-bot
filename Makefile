# Meeting Bot — development tasks. `make check` runs exactly what CI runs.

.PHONY: check lint type test swift-build swift-lint swift-test \
        ios-project ios-build ios-test ext-check ext-test ext-package app models clean

# Full quality gate. Order matters: swift-build runs before `test` so the
# `mbot doctor` test finds the freshly built release audiocap binary.
check: lint type swift-build test swift-lint swift-test ext-check ext-test ios-test
	@echo "\n✓ all checks passed"

lint:
	uv run ruff check meetingbot tests scripts
	uv run ruff format --check meetingbot tests scripts

type:
	uv run mypy

# Coverage-gated unit tests. Coverage source is scoped via [tool.coverage.run] in
# pyproject (NOT a --cov=meetingbot CLI arg — see the note there).
test:
	uv run pytest --cov --cov-report=term-missing --cov-fail-under=80

swift-build:
	cd mac && swift build -c release

swift-lint:
	cd mac && swift format lint --strict --recursive Sources

swift-test:
	cd mac && swift test

# Type-check the browser extension (tsc --noEmit). Installs deps on first run.
ext-check:
	cd chrome-extension && { [ -d node_modules ] || npm ci; } && npm run check

# Unit-test the browser extension (node --test).
ext-test:
	cd chrome-extension && { [ -d node_modules ] || npm ci; } && npm run test

# Package the extension into a Web Store-ready zip (production files only).
ext-package:
	bash scripts/build-extension.sh

# Generate the iOS Xcode project from project.yml (needs `brew install xcodegen`).
ios-project:
	@command -v xcodegen >/dev/null || { echo "xcodegen not found — run: brew install xcodegen"; exit 1; }
	cd ios/MB && xcodegen generate

# Compile the iOS app for the simulator (no signing needed).
ios-build: ios-project
	cd ios/MB && xcodebuild -project MB.xcodeproj -scheme MB -sdk iphonesimulator \
	  -destination 'generic/platform=iOS Simulator' -derivedDataPath .build \
	  CODE_SIGNING_ALLOWED=NO build

# Build + run the iOS unit tests on the first available iPhone simulator.
ios-test: ios-project
	@UDID=$$(xcrun simctl list devices available iPhone | grep -oE '[0-9A-Fa-f-]{36}' | head -1); \
	if [ -z "$$UDID" ]; then echo "no iOS simulator available"; exit 1; fi; \
	echo "▸ iOS tests on simulator $$UDID"; \
	cd ios/MB && xcodebuild -project MB.xcodeproj -scheme MB -sdk iphonesimulator \
	  -destination "id=$$UDID" -derivedDataPath .build CODE_SIGNING_ALLOWED=NO test

# Build the distributable MB.app bundle (macOS).
app:
	bash scripts/build-app.sh

# Benchmark all Whisper model variants (downloads models on first run).
models:
	uv run python scripts/model_matrix.py

clean:
	rm -rf mac/.build chrome-extension/node_modules .venv dist/MB.app ios/MB/.build ios/MB/MB.xcodeproj
