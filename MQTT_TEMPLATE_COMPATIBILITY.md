# MQTT template compatibility — CleanUpInSyncoidSnapshots 0.0.19

The supplied updated syncerate-mqtt-template.zip was inspected on 2026-10-27. verification/template-compatibility.json records its SHA-256 fingerprint and the exact publisher/card comparisons.

## Completion JSON and HA automation

modules/mqtt_status.py is byte-identical to the updated template’s completion module 1.1.0. The cleanup adapter emits the complete typed contract: status is success/failure, success is a real boolean, exit_code is an integer (0 for success, nonzero for failure), with title/name/job, warning, error, bounded stderr and metadata. The existing plain HA automation and configurable blueprint consume these reports. Real cleanup success and checked-failure JSON is tested against their conditions; inconsistent or live-progress packets cannot take their success/failure branches.

The template update adds a Pushover consumer example and compatibility notes, without changing the publisher or card contract. That optional consumer can read these same completion fields after its topic and existing Pushover action are configured. No Pushover messages or other external notifications were sent during verification.

The supplied notes list homeassistant/CleanUpInSyncoidSnapshots/Ubuntu-ZFS-Import/status for the cleanup step. The new complete config-ubuntu-zfs-import-example.json uses exactly that topic. The existing examples retain homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status. Topics are case-sensitive: choose the profile matching your actual HA trigger. No assumption is made that either example is already your deployed config.

The Ubuntu profile defaults to dry-run with every external channel disabled. When enabled, completion.on_success=true keeps both real outcomes eligible, while completion.send_on_dry_run=false suppresses preview events. This avoids feeding preview reports into a real-job sequence. Existing command chains, schedules, readiness checks and continue-after-failure policies are not changed or installed.

## Manufacturer-based Markdown recognition

modules/ha_live_preview.py is byte-identical to the updated template’s live module 1.2.0. The app’s manufacturer default, full config examples and both automatic card variants use exactly CleanUpInSyncoidSnapshots.

The Markdown card’s recognition algorithm matches the supplied project:

1. Scan sensor devices and compare the HA device manufacturer to the configured manufacturer string.
2. Deduplicate matching devices.
3. Resolve aggregate sensors by live_preview_role=status or last_result, with the template’s label fallback before initial packets arrive.
4. Read the full payload attributes to populate fields. A job/device display name is not the grouping identity. Renamed entity IDs and newly discovered jobs remain supported.
5. Prefer a current running state over older retained history, preserve unknown measurements, and mark a known newer run with lost heartbeat unknown rather than claiming an old success.

Both card files match the updated template after only substituting the script manufacturer and the setup comment. They contain no fixed per-job entity-ID list. The original fixed-entity entities/gauge dashboard remains a separate optional layout.

The optional Ubuntu profile and the existing profile have distinct device IDs but the same script manufacturer, so one automatic card recognizes both. A device whose display name says CleanUpInSyncoidSnapshots but whose manufacturer differs is excluded; this is explicitly rendered in a regression check.

Enable live publishing and discovery, and run a job once to publish metadata/state. Actual dry-run live packets additionally require live.send_on_dry_run=true. These gates are independent of completion reporting. If manufacturer is deliberately customized, use that exact string in the card selector too.

## Verification limits

Offline tests use actual discovery payload templates and synthetic HA registry helpers, plus local fake MQTT brokers and rebuilt executable workers. No live HA instance, deployed sequencing automation, production ZFS job, broker/TLS endpoint or Pushover integration was run. Full results and package-preservation evidence are in VERIFICATION.md and verification/.
