# Versioning

## Release rules

Every delivered version increments by 0.0.1. Patch values range from 0 to 99:
0.0.98 → 0.0.99 → 0.1.0 → 0.1.1. Never create 0.0.100.
Record every release's code and documentation changes here. Keep README.md about
current usage and commented_code_map.md about current implementation.
The application version is `__version__` in CleanUpInSyncoidSnapshots.py.

The supplied archive had no version identifier or version history. It is the
unversioned baseline; 0.0.1 is the first numbered release, with no invented prior releases.

## 0.0.14 — 2026-10-02

### Enforce a single-file `dist/` build output

- Bump the application/package version from 0.0.13 to 0.0.14.
- Harden `build-pyinstaller.sh` so every build removes the previous `dist/` directory and recreates it empty before PyInstaller starts.
- Pass explicit `--distpath` and `--workpath` locations so the final executable output and temporary PyInstaller work files cannot be mixed.
- Add a strict post-build manifest guard: a successful build requires `dist/` to contain exactly one entry, `dist/CleanUpInSyncoidSnapshots`, and that entry must be a regular executable file. Any extra file, directory, or hidden entry causes the build to fail.
- Keep the existing frozen `--version` and `--help` smoke checks after the single-file `dist/` validation.
- Extend the PyInstaller regression test and current-use documentation/code map to enforce and explain the empty-before-build / executable-only-after-build rule.

### Preserved safety behavior

No cleanup, snapshot selection/destruction, dry-run, retention, dataset continuation, mail, MQTT, Home Assistant, configuration, or runtime notification behavior changed. This release only hardens the PyInstaller build-output layout.

### Verification

See `VERIFICATION.md` for automated, CLI, shell-syntax, manifest, and packaging checks plus the explicit limitation on producing a real frozen binary in this environment.

## 0.0.13 — 2026-10-02

### Add standalone PyInstaller release build

- Bump the application/package version from 0.0.12 to 0.0.13.
- Add `CleanUpInSyncoidSnapshots.spec` for a one-file PyInstaller build. The spec explicitly collects all Paho MQTT and Tomli submodules so the frozen runtime contains the optional MQTT implementation and TOML fallback instead of depending on separate runtime Python packages.
- Add `requirements-build.txt`, which installs the normal MQTT dependency set, forces Tomli into the build environment, and installs PyInstaller.
- Add `build-pyinstaller.sh`. It recreates a clean `.venv-build`, installs the complete build requirements, clears old `build/` and `dist/` output, builds the one-file executable, and smoke-tests its `--version` and `--help` actions.
- Keep the final executable directly at `dist/CleanUpInSyncoidSnapshots`; no second `bin/` copy is created.
- Add frozen-runtime path handling so persistent logs live beside the installed executable rather than inside PyInstaller's temporary one-file extraction directory. Source-mode log placement remains beside `CleanUpInSyncoidSnapshots.py`.
- Make the timeout-isolated MQTT worker compatible with a frozen executable. Source mode still launches `mqtt_notifications.py --publish`; frozen mode relaunches the same executable with a private environment marker while report/config data and credentials remain on stdin instead of argv.
- Add regression coverage for frozen runtime paths, frozen MQTT worker relaunching, the private worker route, dependency collection, clean build-environment creation, and the required `dist/` output path.
- Update README/current code map with the build command, frozen run command, bundled-vs-external dependency boundaries, and `dist/` layout.

### Preserved safety behavior

Snapshot matching, dry-run no-destroy behavior, one-snapshot-at-a-time `zfs destroy`, retention, dataset continuation, mail/MQTT `on_success` rules, notification failure handling, and Home Assistant report behavior are unchanged. The PyInstaller changes only add an alternate packaging/runtime form and the minimum frozen-specific process/path adaptations required to preserve existing behavior.

### Verification

See `VERIFICATION.md` for source regression/CLI checks and the explicit limitation that this verification environment could not download PyInstaller/Paho/Tomli, so an actual frozen executable could not be produced here.

## 0.0.12 — 2026-10-02

### Make mail success-suppression reporting match MQTT

- Bump the application/package version from 0.0.11 to 0.0.12.
- Change the local mail suppression message to `Success mail report suppressed by mail.on_success=false.` so it mirrors `Success MQTT report suppressed by mqtt.on_success=false.`.
- The message is emitted after every successful run, including both normal delete mode and dry-run, whenever mail is enabled and `mail.on_success=false`.
- Notification behavior itself is unchanged: suppressed successes send neither mail nor MQTT; failures still notify through each enabled channel regardless of `on_success`.
- Add regression coverage for the exact mail suppression message in both delete and dry-run modes.

### Preserved safety behavior

No snapshot selection, destruction, dry-run safety, dataset continuation, log retention, mail delivery, MQTT delivery, or Home Assistant behavior changed in this release.

### Verification

See `VERIFICATION.md` for the final automated, CLI, documentation, manifest, and package checks.

## 0.0.11 — 2026-10-02

### Harden success-notification suppression for dry-run

- Bump the application/package version from 0.0.10 to 0.0.11.
- Add one shared `should_send_notification(success, on_success)` policy helper and use it for both
  mail and MQTT decisions. Failure remains notification-on for every enabled channel; success remains
  opt-in through that channel's `on_success=true`.
- Apply the MQTT success gate in `main()` before `notify_mqtt` is called. This means a successful
  delete or dry-run with `mqtt.on_success=false` does not enter the MQTT notification path at all.
- Keep the existing defensive gate inside `notify_mqtt` as a second layer, so direct/internal callers
  also cannot publish successful reports while `on_success=false`.
- Apply the same shared helper to mail success/failure selection, including the root-check failure
  path, so mail and MQTT use one truth table instead of separate policy expressions.
- Log explicit local suppression messages after successful runs when an enabled channel has
  `on_success=false`. This makes it visible in the local report why no success notification was sent.
- Add an end-to-end regression for the reported case: successful `dry-run`, mail enabled, MQTT
  enabled, and `on_success=false` on both must invoke neither notification path.
- Add the paired failure regression proving a failed dry-run still invokes both enabled channels
  when both `on_success=false`, preserving the requested failure behavior.
- Update current-use documentation, code map, config comments, and verification evidence.

### Preserved safety behavior

Dry-run reporting and snapshot/log selection are unchanged. Dry-run still never calls `zfs destroy`
or removes old logs. Dataset continuation, final failure semantics, root enforcement, one-snapshot-at-a-time
destruction, mail/MQTT enablement, non-retained MQTT transport, and notification-delivery failure handling
remain unchanged.

### Verification

See `VERIFICATION.md` for the final automated, CLI, documentation, manifest, and package checks.

## 0.0.10 — 2026-10-02

### Unified success notifications and complete dry-run reporting

- Bump the application/package version from 0.0.9 to 0.0.10.
- Give MQTT the same `on_success` setting already used by mail. For either notification channel,
  `enabled=true` + `on_success=false` means failure-only notifications, while `on_success=true`
  also enables success notifications.
- Apply the same rule to normal delete runs and dry-run previews. A successful dry-run is silent on
  a channel unless that channel's `on_success=true`; a failed dry-run is still reported through every
  enabled channel regardless of `on_success`.
- Replace the old MQTT-only `publish_dry_run` setting with `mqtt.on_success`. Configs still using
  `publish_dry_run` fail validation with a targeted migration message instead of being accepted with
  ambiguous semantics.
- Add a final dry-run report with configured/completed dataset counts, dataset failure count, matching
  snapshot count, total snapshots that would be deleted, per-dataset counts, and old-log retention
  candidate counts. The report explicitly records that zero snapshots were actually destroyed.
- Make snapshot pruning return aggregate selection counts and make log-retention processing return
  selected log-group/file counts so the final report is based on the same selection logic used by the
  cleanup itself rather than duplicated calculations.
- On successful dry-runs, preview old-log retention before writing/sending the final report. This keeps
  dry-run non-destructive while ensuring success email and MQTT reports include the log-retention
  preview. Normal delete-run finalization order remains unchanged so mail can still use the current logs
  before old-log pruning.
- Add the aggregate `dry_run_report` object to MQTT dry-run payloads. Update the Home Assistant
  receive-only blueprint to display those counts when present.
- Give dry-run mail distinct `DRY-RUN SUCCESS` / `DRY-RUN FAILED` subjects and report-oriented body
  text while preserving the existing failure-always / success-opt-in rules.
- Extend regression coverage for mail/MQTT success gating, failure delivery during dry-run, dry-run
  aggregate counts, log-retention counts, the MQTT report object, the Home Assistant blueprint, and the
  removed `publish_dry_run` migration error.
- Update `README.md`, `commented_code_map.md`, `config-example.toml`, and `VERIFICATION.md` for the
  current 0.0.10 behavior.

### Preserved safety behavior

Dry-run still never calls `zfs destroy` and never removes old log files. Snapshot matching, retention
selection, exact configured hostname matching, one-snapshot-at-a-time destruction, no-shell ZFS
execution, root enforcement, dataset continuation/final-failure semantics, deterministic log location,
non-retained MQTT publishing, timeout-isolated MQTT delivery, and optional notification channels remain
intact. Notification-delivery failures remain nonfatal to the cleanup result.

### Verification

See `VERIFICATION.md` for automated tests, compile/CLI checks, manifest/package checks, and live-system
limitations.

## 0.0.9 — 2026-10-02

### Release-hygiene correction and workflow baseline

- Bump the application/package version from 0.0.8 to 0.0.9.
- Correct the shipped `.gitignore` example exceptions so `datasets-example`, `hostnames-example`,
  and `config-example.toml` are actually unignored. The 0.0.8 archive used malformed `! ` rules
  and referenced `config-example.json`, causing its own TOML-example regression test to fail.
- Expand `.gitignore` to cover Python bytecode/cache directories, virtual environments, test/tool
  caches, build/dist/egg-info outputs, coverage output, and common temporary/editor files. This
  aligns repository hygiene with the release rule that generated cache/build/temp artifacts must
  not be packaged.
- Strengthen the existing `.gitignore` regression test so it protects the corrected example
  exceptions, required cache/build/temp exclusions, and rejects malformed spaced negation rules.
- Keep runtime cleanup, retention, ZFS command selection, continuation behavior, logging, mail,
  MQTT transport/schema, Home Assistant blueprint behavior, and TOML schema unchanged.
- Keep `config-example.toml` unchanged because no runtime setting was added or removed and its
  schema coverage test still verifies every supported option.
- Preserve the supplied disclaimer text and project-specific data-loss warning unchanged.
- Update README.md and commented_code_map.md for the current 0.0.9 release and refresh
  `VERIFICATION.md` with the actual baseline discrepancy and final release checks.
- Keep the project manifest at the same 17 relative project files as the supplied 0.0.8 archive.

### Preserved safety behavior

Snapshot matching, exact configured hostname matching, dry-run protection, one-snapshot-at-a-time
`zfs destroy`, no-shell ZFS execution, root enforcement, dataset-failure continuation/final-failure
semantics, deterministic log location, optional mail/MQTT behavior, non-retained MQTT publishing,
and the timeout-isolated MQTT worker are unchanged.

### Verification

See `VERIFICATION.md` for baseline findings, final tests, CLI/compile checks, manifest/package checks,
and live-system limitations.

## 0.0.8 — 2026-09-28

### Configurable continuation for missing and other ZFS dataset failures

- Bump the application/package version from 0.0.7 to 0.0.8.
- Add two strict `[cleanup]` TOML booleans, both defaulting to `true` even when omitted:
  - `continue_on_missing_dataset` controls whether the explicit ZFS `dataset does not exist`
    failure continues with the next configured dataset.
  - `continue_on_other_failures` controls whether other checked ZFS `list` or `destroy`
    failures continue with the next configured dataset.
- Keep every encountered dataset-level ZFS failure as an overall failed run. Continuation only decides
  whether later configured datasets are attempted; it never turns a failed command into success.
- Replace the missing-only final error container with `DatasetFailuresError`, which can aggregate both
  missing and other checked ZFS failures and preserve their original stderr for MQTT reporting.
- When continuation is disabled for the matching failure category, stop immediately after recording the
  failure and report it through the same final mail/MQTT failure paths.
- When continuation is enabled, continue at the next configured dataset. A failed `zfs destroy` still
  stops further snapshot work inside the current dataset before the outer dataset loop continues.
- Keep global/config/root/input/process-start failures and interrupts outside these continuation switches.
- If mail is enabled, any dataset failure uses the existing FAILED-mail path whether it was continued or
  stopped immediately.
- If MQTT is enabled, failure reports are now published even during `dry-run`; `publish_dry_run=false`
  suppresses only successful dry-run previews. The MQTT JSON schema and status names are unchanged.
- Keep failed runs from pruning old log groups so the failure evidence remains available.
- Update the complete config example, README current-use documentation, code map, verification evidence,
  and regression tests for both `true` and `false` behavior.

### Preserved safety behavior

Snapshot matching, retention selection, exact configured hostname matching, one-snapshot-at-a-time
`zfs destroy`, no-shell command execution, root enforcement, dry-run no-destroy behavior, mail/MQTT
opt-in, non-retained MQTT publishing, timeout-isolated MQTT delivery, Home Assistant JSON contract,
and deterministic log location remain unchanged except for the requested continuation/notification rules.

### Verification

See `VERIFICATION.md` for the full test, compile/CLI, manifest, and package checks plus live-system limits.

## 0.0.7 — 2026-09-28

### CLI/version, disclaimer, and release-hygiene maintenance

- Bump the application/package version from 0.0.6 to 0.0.7.
- Add a public `--version` argparse action. It prints the application name/version and exits
  successfully before configuration loading, log creation, root checks, notifications, or ZFS work.
- Expand the custom usage banner and `--help` output so `--version` is visible alongside the
  existing `-h/--help` and `-c/--config CONFIG` flags. No cleanup/retention behavior moved back
  onto the CLI; operational settings still come only from TOML.
- Add regression tests that protect both `--version` and its presence in `--help`.
- Correct `.gitignore` so `config-example.toml` is explicitly kept even though site-local
  `config*` files remain ignored; add a regression test for that packaging/repository rule.
- Replace the previous general liability text with the project owner's supplied disclaimer text,
  retaining project-specific data-loss and no-license notes after it.
- Update README.md for current 0.0.7 usage only, including the complete public flag table and
  the version command. Update commented_code_map.md with the new flag and tests.
- Keep `config-example.toml` unchanged because its schema test confirms it already contains
  every supported setting and remains safe by default with `command = "dry-run"`.
- Keep the 17-file project manifest unchanged: no project file was added or removed.

### Preserved behavior

Snapshot matching, retention calculation, dry-run protection, one-at-a-time `zfs destroy`, root
enforcement, missing-dataset continuation/final-failure behavior, TOML validation, mail behavior,
MQTT transport/schema, Home Assistant blueprint behavior, log location, and log retention remain
unchanged from 0.0.6.

### Verification

See VERIFICATION.md for the 47-test result, compile/CLI checks, manifest/package checks, and
remaining live-ZFS/mail/MQTT/Home Assistant limitations.

## 0.0.6 — 2026-09-25

### Missing-dataset continuation with failed overall result

- Detect the explicit ZFS `dataset does not exist` stderr returned by the per-dataset
  `zfs list -H -t snapshot -o name DATASET` command.
- Record that dataset as missing and continue processing every later configured dataset
  instead of aborting the whole run immediately.
- Keep the overall result failed when any configured dataset is missing: final process exit
  remains code 1, failure mail is sent when mail is enabled, and MQTT keeps the existing
  `status = "failure"` / `exit_code = 1` contract used by Home Assistant automation logic.
- Reuse the existing MQTT JSON schema. No fields or status values were changed. The existing
  `error` field now clearly states which ZFS dataset(s) were missing, while the existing
  `stderr` field carries the original bounded ZFS `dataset does not exist` diagnostic.
- Make the failure-mail intro explicitly identify a missing-dataset partial failure and state
  that later configured datasets were still processed. The `.err` attachment still contains
  the original command failure plus the specific continuation/final-failure log entries.
- Keep all other checked ZFS failures immediately fatal, including permission/pool/I/O/list
  failures not matching the explicit missing-dataset diagnostic and all `zfs destroy` failures.
- Do not prune old log groups after a missing-dataset run because the run is not successful.
- Add lifecycle regression coverage for a missing first dataset followed by two valid datasets,
  verifying all three are attempted and the final mail/MQTT/exit outcome is still failure.
- Update README.md, commented_code_map.md, config-example.toml, and VERIFICATION.md for the
  current behavior.

### Preserved behavior

Snapshot matching, retention calculation, one-at-a-time snapshot destruction, dry-run deletion
protection, root enforcement, TOML configuration, mail opt-in, MQTT transport/schema/status names,
Home Assistant blueprint contract, and non-missing-error handling remain unchanged.

### Verification

See VERIFICATION.md for automated tests, compile/CLI checks, package-manifest comparison, and
remaining live-ZFS/mail/MQTT/Home Assistant limitations.

## 0.0.5 — 2026-09-25

### CLI help and documentation maintenance

- Restore standard argparse `-h` / `--help` so users can inspect the supported CLI
  without supplying a configuration file or starting cleanup.
- Add `--config CONFIG` as a long-form alias for the existing `-c CONFIG` selector.
  Both forms load the same TOML configuration and enter the same validated cleanup lifecycle.
- Keep all operational settings in TOML; legacy options such as `--command` remain rejected.
- Add help examples for the short and long configuration selector.
- Add regression tests confirming help exits successfully without calling cleanup, the long
  alias reaches the same TOML loader/lifecycle, and old operational flags are still rejected.
- Update README.md so every public flag is described with purpose and usage examples.
- Update `config-example.toml` with both supported configuration-selector spellings and the
  non-destructive help command.
- Refresh `.gitignore` for the current TOML-only project: preserve the shipped example while
  ignoring local `config*.toml`, Python bytecode/cache, virtualenv, build, distribution, and
  generated log directories. Remove stale JSON/MQTT-config ignore entries from older layouts.
- Update commented_code_map.md and VERIFICATION.md for the current implementation and checks.
- Correct the old verification manifest count: the supplied 0.0.4 archive contains 17 project
  files (including `.gitignore`), and 0.0.5 preserves the same 17 relative file paths.
- Keep the supplied `DISCLAIMER.md` in the package and link to it from the README safety notes.

### Preserved behavior

Snapshot matching, dry-run/delete selection, root enforcement, retention rules, log location,
mail behavior, MQTT schema/delivery behavior, TOML validation, and ZFS command construction are
unchanged. The CLI change only improves discovery and adds an equivalent long spelling for the
existing configuration selector.

### Verification

See VERIFICATION.md for automated tests, compile/CLI checks, manifest comparison, archive
integrity checks, and the items that were not exercised against live ZFS/mail/Home Assistant.

## 0.0.4 — 2026-09-16

### Log directory fix

- Fix log placement so every run creates and uses `logs/` beside the actual
  `CleanUpInSyncoidSnapshots.py` file.
- Remove the old `/tmp/<script-name>` fallback. A permissions/filesystem error while
  creating the script-local `logs/` directory now fails visibly instead of silently
  relocating logs.
- Resolve the script location with `os.path.realpath(__file__)`, so invoking the program
  through a symlink still places logs beside the actual script file.
- Keep existing `.log`/`.err` naming, log retention, mail attachments, and cleanup
  behavior unchanged; they now all operate against the deterministic script-local folder.
- Add regression coverage that verifies `logs/` is created beside the actual script.
- Update README.md, `config-example.toml`, commented_code_map.md, VERIFICATION.md, and
  package metadata for 0.0.4.

### Preserved behavior

TOML configuration, the single `-c CONFIG` CLI, snapshot matching/deletion safety,
dry-run protection, retention rules, optional mail, and MQTT reporting are unchanged.

### Verification

See VERIFICATION.md for compile/tests, CLI checks, fixed log-location regression, and
release-package verification.

## 0.0.3 — 2026-09-15

### Configuration and CLI changes

- Replace the operational multi-flag CLI with one required public option: `-c CONFIG`.
- Move cleanup mode, dataset/hostname file paths, retention, log prefix, report metadata,
  email settings, and all MQTT settings into one TOML configuration file.
- Add `config-example.toml` containing every supported setting with inline comments.
- Default the example to `command = "dry-run"`, `mail.enabled = false`, and
  `mqtt.enabled = false` so copying the example does not enable destructive cleanup
  or notification delivery by itself.
- Resolve configured input files and MQTT certificate/key paths relative to the TOML
  file when paths are not absolute.
- Reject unknown TOML sections/options and invalid required values before any cleanup
  logging, mail, MQTT publishing, or ZFS command is started.
- Preserve the earlier negative-retain behavior by normalizing negative
  `cleanup.retain_count` values to zero.
- Preserve the original `Nd`/`Nw`/`Nm` age syntax and 30-day month behavior.

### MQTT and mail changes

- Replace the separate MQTT JSON configuration path with the `[mqtt]` TOML section.
- Keep MQTT opt-in through `mqtt.enabled`; the existing bounded worker, non-retained
  publish behavior, QoS handling, TLS/auth support, dry-run publish opt-in, report
  schema, and nonfatal delivery failure policy remain in place.
- Support plain TOML string credentials, including `password = "<String>"`.
- Normalize empty optional MQTT strings to disabled/absent values where the previous
  JSON configuration used `null`.
- Move email enablement, recipient, and success-notification policy into `[mail]`.
- Keep mail disabled unless explicitly enabled, and keep mail delivery failures nonfatal.

### Compatibility, documentation, and packaging changes

- Bump the application/package version to 0.0.3.
- Add `config_loader.py` so TOML parsing/validation is isolated from destructive ZFS logic.
- Keep Python 3.10 compatibility through `tomli`; Python 3.11+ uses standard `tomllib`.
- Add `requirements.txt` for the Python 3.10 TOML compatibility dependency and make
  `requirements-mqtt.txt` include the base requirements before Paho MQTT.
- Remove obsolete `mqtt-config-example.json`; its settings are now represented in
  `config-example.toml`.
- Update the Home Assistant blueprint description to point at `[mqtt].topic` in TOML.
- Rewrite README.md for current TOML-only usage and document the single remaining
  public CLI option plus every TOML setting.
- Update commented_code_map.md for all current functions, test helpers, commands, and files.
- Expand regression coverage for TOML schema completeness, config-relative paths,
  CLI rejection of old flags, mail opt-in validation, plain-string MQTT passwords,
  and lifecycle behavior through the new config path.

### Preserved safety behavior

Snapshot matching, exact-host filtering, nonrecursive `zfs list`, one-at-a-time checked
`zfs destroy`, root enforcement, dry-run destruction protection, retention rules, log
pruning rules, error propagation, optional mail behavior, and MQTT result reporting
remain routed through the existing cleanup functions. No shell invocation was added.

### Verification

See VERIFICATION.md for completed compile/tests, CLI checks, manifest comparison, and
remaining environment limitations.

## 0.0.2 — 2026-09-15

### Application/package changes

- Bump the application/package version to 0.0.2.
- Add a Home Assistant automation blueprint example at
  `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`.
- The blueprint subscribes to the configured MQTT result topic, validates the
  application/status fields, and creates Home Assistant persistent notifications.
- Distinguish clean success, success-with-warning, failure, and dry-run reports.
- Add blueprint inputs to independently enable/disable success, warning, failure,
  and dry-run notifications and to choose whether the newest notification replaces
  the previous one by `notification_id`.
- Keep the blueprint receive-only: it does not publish MQTT, start cleanup, invoke
  ZFS, or change backup sequencing.
- Document blueprint installation/configuration and retain the manual integration
  example for users who prefer an existing combined Syncerate/backup automation.
- Add regression checks for the blueprint's topic input, report validation,
  persistent-notification action, and report fields.

### Preserved behavior

Snapshot selection/deletion, root enforcement, dry-run protections, email, log
retention, MQTT report schema, MQTT transport, and MQTT failure handling are
unchanged from 0.0.1.

### Verification

See VERIFICATION.md for the completed checks and release-package evidence.

## 0.0.1 — 2026-09-15

### Code changes

- Add optional `--mqtt-config FILE` and `--version` CLI options and `__version__`.
- Add mqtt_notifications.py: strict JSON configuration validation, certificate-path
  resolution, Home Assistant-compatible status JSON, and one-shot Paho publishing.
- Support broker host/port, username/password, client ID, QoS 0/1/2, timeout,
  verified TLS, CA certificates, optional client certificate/key, and dry-run opt-in.
- Always publish non-retained reports; suppress dry-run reports by default.
- Use a separate Python worker with credentials/report on stdin and a bounded
  subprocess timeout, so stalled DNS/connections/acknowledgements cannot block indefinitely.
- Keep publisher failures nonfatal and avoid logging worker output or credentials.
- Extract the existing execution body into run_cleanup(args, state). Keep main()
  responsible for CLI/config parsing and final reporting after execution and finalization.
- Report success/failure for normal completion, exceptions, root rejection, and
  caught keyboard interrupts. Preserve existing cleanup exceptions and exit outcomes.
- Add ReportWarningHandler to remember logged errors for the JSON warning boolean,
  including errors whose log files may later be removed by retention.
- Reuse backup title/comment and existing CommandError diagnostics in MQTT reports.
- Remove the duplicate script_base_name definition and retain its existing equivalent helper.
- Correct `--command` help to explain both commands and remove the inaccurate
  claim that every non-root log path is a fallback.
- Add requirements-mqtt.txt and regression tests, including real Paho loopback
  protocol tests and mocked cleanup/mail/TLS scenarios.

### Documentation and package changes

- Replace stale README app/script names and Python requirement with current usage.
- Document every CLI flag, all MQTT settings, JSON fields, dry-run side effects,
  existing retention edge cases, notification limits, and Home Assistant integration steps.
- Add a complete MQTT config example without real credentials.
- Add commented_code_map.md with each function/method, command, and file explained.
- Add this release record and VERIFICATION.md with test and package evidence.
- Preserve original legal/disclaimer text in DISCLAIMER.md and link it from README.md.
- Preserve .github/CODEOWNERS, datasets-example, and hostnames-example byte-for-byte.

### Preserved behavior

Snapshot selection, age/count rules, root restriction, dry-run deletion protections,
nonrecursive ZFS invocation, email policy, log retention, and error propagation
remain intact. In particular, no age limit plus zero retention still selects all
matching snapshots for deletion; only its incorrect README description was corrected.
The existing zero-duration snapshot-cutoff behavior is also documented, not changed.

### Verification

See VERIFICATION.md for the completed checks and remaining environment limitations.
