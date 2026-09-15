# Versioning

## Release rules

Every delivered version increments by 0.0.1. Patch values range from 0 to 99:
0.0.98 → 0.0.99 → 0.1.0 → 0.1.1. Never create 0.0.100.
Record every release's code and documentation changes here. Keep README.md about
current usage and commented_code_map.md about current implementation.
The application version is `__version__` in CleanUpInSyncoidSnapshots.py.

The supplied archive had no version identifier or version history. It is the
unversioned baseline; 0.0.1 is the first numbered release, with no invented prior releases.

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
