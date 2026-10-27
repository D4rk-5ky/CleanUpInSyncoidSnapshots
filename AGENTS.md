# Project maintenance workflow

Apply the user's requested workflow to this project:

- Inspect the complete current project before changing code, including modules, tests, configuration/examples, Home Assistant files, build/dependency files and documentation.
- Preserve every necessary original/current project file. Do not remove files unless the user explicitly requests removal. Document authorized relocations in the release manifest comparison.
- Reuse existing functions/modules instead of duplicating logic. Keep supporting application modules in `modules/`.
- Preserve safety and cleanup behavior unless the user explicitly authorizes a change, including root enforcement, exact snapshot destruction, dry-run behavior, failure continuation semantics and separate completion/live reporting switches.
- Each delivered version increases by 0.0.1. Roll over 0.0.99 to 0.1.0; never create 0.0.100. Use one application version consistently in source, examples and release documentation.
- Keep README.md about current usage/settings/commands only. Explain every public flag and build/setup command. Keep --help descriptive and expose --version without requiring configuration or cleanup.
- Keep commented_code_map.md current and explain what every function/method and command does and why it exists, including internal workers and build commands.
- Record every release's code/documentation changes and preserved behavior in VERSIONING.md. Preserve earlier release entries and keep the lowercase versioning.md mirror byte-identical.
- Keep complete safe config examples with all supported options, including independent HA live preview. Keep the supplied disclaimer wording intact in DISCLAIMER.md and present it in README with correct project names/links.
- Run suitable regression tests, compilation and harmless source/frozen CLI checks where possible. Do not run production ZFS destruction or send production notifications for verification.
- Package the entire project, including required original files and new deliverables, into a clean ZIP. Exclude __pycache__, .pyc, .pyo, build/environment/cache directories and temporary files.
- Compare the final ZIP manifest against both the original supplied archive and the previous release. Account explicitly for preserved, changed, added and authorized moved files, and check ZIP integrity/content and executable modes.
- Report concrete changes, completed verification and testing limitations clearly.
