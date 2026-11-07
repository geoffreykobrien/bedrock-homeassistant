# Changelog

To release: bump `version` in `manifest.json` (plus `VERSION` in `const.py` and
`CARD_VERSION` in the card), add a section below, and push to `main`. The Release
workflow tags it and HACS picks it up.

## 0.1.1

### Fixed
- **Players now show for Bedrock servers.** Crafty doesn't set a log file for Bedrock servers by default, so the integration read an empty log. It now falls back to Crafty's live console buffer and tracks joins and leaves across polls, so players stay listed after their join line scrolls out of the buffer. The list resets when the server restarts.
- Server devices are now linked to the Crafty hub with `via_device_id`, which removes a deprecation warning on Home Assistant 2026.11.
- A bad API token (which Crafty reports as `403 ACCESS_DENIED`) now shows "invalid token" during setup and triggers re-authentication.

### Added
- One-time log warnings that name the missing Crafty permission when stats or logs are denied.
- README section on creating the API token and which permission each feature needs.

## 0.1.0

- Initial release: config, reconfigure, reauth and options flows; per-server sensors, switch, buttons and player event entity; `send_command` service; diagnostics; auto-registered `crafty-server-card`.
