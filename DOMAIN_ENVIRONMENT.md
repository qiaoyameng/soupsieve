# Reproducible offline environment

Upstream: https://github.com/facelessuser/soupsieve
Upstream SHA: f7795804d07b6b90a8341782c9640acf376761b9
Runtime: 3.13.14 (tags/v3.13.14:fd17997, Jun 10 2026, 13:03:48) [MSC v.1944 64 bit (AMD64)]
Platform: win32

Create an isolated virtual environment, then run from this checkout:
```
python -m pip install -r requirements-domain.lock
python -m pip install -e .
```
Set `PYTHONUTF8=1` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` before tests.
```
python -m pytest -q -o addopts= -o log_cli=false tests/test_api.py tests/test_extra tests/test_level4
```
Measured selected pytest process: 6.65 seconds.
Only BeautifulSoup with the standard-library html.parser is installed; lxml/html5lib-specific cases are upstream skips.

Tests use synthetic in-memory or temporary-file inputs under the upstream license.
No account, cloud service, browser or external database is needed. Recreate the
environment from this immutable commit to reset the starting state.
