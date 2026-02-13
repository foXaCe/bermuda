# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-02-13

### Added
- Complete translation system with French (fr) support for all config/options flow strings
- `strings.json` as translation source of truth
- `icons.json` for entity and service icon translations (Gold Quality Scale rule)
- Dynamic UI text translations (EN/FR) for options flow tables and descriptions

### Changed
- Replace hardcoded English text in options flow with translation system
- Move dynamic description texts to inline dict (hassfest schema compliance)
- Use `{github_url}` placeholder instead of hardcoded URL in config step
- Add `PARALLEL_UPDATES = 0` to sensor, device_tracker, and number platforms (Silver rule)
- Use `@dataclass(slots=True)` on BermudaData for memory optimization
- Add French words to codespell ignore list
- Clean up excessive debug logging across codebase

### Fixed
- `sensor.py`: Use `_attr_translation_key` instead of `self.name` for i18n-safe comparisons
- `config_flow.py`: Use proper error dict pattern for scanner record errors
- `test_bermuda_advert.py`: Fix fixture options using wrong key names for constants
- CI: Remove invalid `options.description_text` section from translation files (hassfest)

### Dependencies
- Bump actions/checkout from 4 to 6
- Bump actions/setup-python from 5.6.0 to 6.2.0
- Bump softprops/action-gh-release from 2.3.2 to 2.5.0
- Bump release-drafter/release-drafter from 6.1.0 to 6.2.0
- Bump sigstore/gh-action-sigstore-python from 3.0.1 to 3.2.0
- Bump ruff from 0.12.7 to 0.15.0
- Bump colorlog from 6.9.0 to 6.10.1
- Bump pre-commit from 4.2.0 to 4.5.1
- Bump black from 25.1.0 to 26.1.0
- Bump pip from 25.2 to 26.0.1
- Bump reorder-python-imports in workflows
