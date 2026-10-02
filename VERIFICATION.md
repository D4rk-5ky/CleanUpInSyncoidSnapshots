# Verification — CleanUpInSyncoidSnapshots 0.0.14

Verification date: 2026-10-02.

## Requested behavior

This release hardens the PyInstaller output layout. Every build must start with an empty `dist/` directory and a successful build must finish with exactly one entry:

```text
dist/CleanUpInSyncoidSnapshots
```

No other file, directory, hidden file, metadata file, or copied support file is allowed in `dist/`.

`build-pyinstaller.sh` now:

1. removes the previous build venv, `build/`, and `dist/`;
2. recreates `dist/` empty;
3. creates the isolated build environment and installs `requirements-build.txt`;
4. runs PyInstaller with explicit `--distpath` and `--workpath` locations;
5. enumerates every direct entry in `dist/` including hidden entries;
6. fails unless the only entry is the regular executable `CleanUpInSyncoidSnapshots`;
7. smoke-tests that executable with `--version` and `--help`.

Temporary PyInstaller work files remain under `build/`, not `dist/`.

## Automated tests

Command:

```text
python3 -B -m unittest discover -s tests -v
```

Result:

```text
Ran 69 tests
OK (skipped=3)
```

That is **66 passed, 3 skipped, 0 failed**.

The three skipped tests are the optional real-Paho MQTT broker/loopback tests because `paho-mqtt` is not installed in this verification environment.

The PyInstaller regression now checks that the build helper:

- deletes the old `dist/` and recreates it;
- uses explicit PyInstaller dist/work paths;
- expects `dist/CleanUpInSyncoidSnapshots`;
- counts all top-level `dist/` entries;
- requires exactly one entry;
- requires that entry to be the expected regular executable;
- retains the frozen `--version` and `--help` smoke checks;
- creates no `bin/` copy.

## Build-output guard simulation

The build helper was exercised with a local fake PyInstaller runner so the shell lifecycle and final-output guard could be tested without downloading external packages.

Clean-output case:

```text
CleanUpInSyncoidSnapshots 0.0.14
Built: .../dist/CleanUpInSyncoidSnapshots
Verified: dist/ contains only CleanUpInSyncoidSnapshots
```

The resulting simulated `dist/` manifest contained exactly:

```text
CleanUpInSyncoidSnapshots
```

Extra-output case: the fake PyInstaller runner additionally created `dist/extra.txt`. The build helper correctly exited with status 1 and reported:

```text
ERROR: dist/ must contain exactly one executable: .../dist/CleanUpInSyncoidSnapshots
Current dist/ contents:
  extra.txt
  CleanUpInSyncoidSnapshots
```

This verifies the new shell-level single-file guard. It is not a substitute for a real PyInstaller freeze.

## Compile, shell, and CLI checks

The following compile successfully with `python3 -m py_compile`:

- `CleanUpInSyncoidSnapshots.py`
- `config_loader.py`
- `mqtt_notifications.py`
- `tests/test_project.py`
- `CleanUpInSyncoidSnapshots.spec` (syntax only)

`bash -n build-pyinstaller.sh` succeeds.

`python3 CleanUpInSyncoidSnapshots.py --version` returns:

```text
CleanUpInSyncoidSnapshots.py 0.0.14
```

`python3 CleanUpInSyncoidSnapshots.py --help` exits successfully and documents the public `-h/--help`, `--version`, and `-c/--config` options.

## Real PyInstaller limitation

A real one-file executable was not produced in this verification environment because PyInstaller, Paho MQTT, and Tomli are not installed here and this environment cannot download them from the external Python package index.

The actual build should therefore be run on the target/compatible Linux build system with:

```text
./build-pyinstaller.sh
```

On that system the script itself will reject any successful-looking build that leaves anything other than the single executable in `dist/`.

## Documentation/config checks

- `README.md` documents the empty-before-build and executable-only-after-build `dist/` rule.
- `VERSIONING.md` records the 0.0.14 release.
- `commented_code_map.md` documents the strict build command and regression behavior.
- `config-example.toml` is unchanged because no runtime configuration changed.
- `DISCLAIMER.md` is unchanged.

## 0.0.13-to-0.0.14 manifest comparison

Both releases contain the same **20 project files**. No project file was added or removed.

Intentionally changed project files:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `build-pyinstaller.sh`
- `commented_code_map.md`
- `tests/test_project.py`

All other project files remain byte-for-byte unchanged from 0.0.13.

`CleanUpInSyncoidSnapshots.py` and `build-pyinstaller.sh` retain executable mode `0755` in the prepared source tree.

## Safety and limitations

No snapshot selection, ZFS destruction, dry-run, retention, dataset continuation, configuration, mail, MQTT, Home Assistant, or notification-policy behavior changed in 0.0.14.

No real ZFS destruction, production mail delivery, production MQTT broker connection, Home Assistant runtime test, or real PyInstaller frozen-runtime test was performed.
