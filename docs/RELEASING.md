# Releasing Forbin

## Prerequisites

- Push access to this repository
- `HOMEBREW_TAP_TOKEN` secret configured in GitHub repo settings (fine-grained PAT with Contents read/write on `chris-colinsky/homebrew-forbin`)

## Release Steps

1. **Bump the version** in `pyproject.toml`:
   ```toml
   version = "0.2.0"
   ```

2. **Commit and push** to `main` (or merge a release branch):
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.2.0"
   git push origin main
   ```

3. **Create and push a tag**:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

   The tag must match the pattern `v*.*.*` to trigger the release workflow.

4. **The GitHub Actions workflow handles the rest**:
   - Runs tests (`uv run pytest`)
   - Builds the package
   - Publishes to PyPI as `forbin-mcp`
   - Creates a GitHub Release with auto-generated notes
   - Updates the Homebrew tap (`chris-colinsky/homebrew-forbin`) — see below

## Homebrew Bottle Build (two-stage)

The Homebrew tap is updated in two stages on every release:

1. **`release.yml` in this repo** writes a fresh `Formula/forbin.rb` (without a `bottle do` block) and pushes it to the tap repo.
2. **`bottles.yml` in `homebrew-forbin`** triggers automatically on that formula change. It:
   - Builds bottles in parallel on `macos-26` (Tahoe) and `macos-15` (Sequoia) runners.
   - Uploads the bottle tarballs to a GitHub Release on the tap repo, tagged `forbin-<version>`.
   - Rewrites the formula to add the `bottle do` block referencing those bottles, and commits with `[skip ci]`.

End users running `brew install` after stage 2 completes get the prebuilt bottle (fast install, no compilation). Between stages 1 and 2 (about 10–15 minutes), `brew install` will fall back to building from source.

The bottle build forces `--no-binary :all:` in the formula's `def install` so every wheel — especially Rust extensions like `pydantic-core`, `cryptography`, `rpds-py`, `watchfiles` — is built locally with `RUSTFLAGS="-C link-arg=-headerpad_max_install_names"`. This works around a Homebrew relocation bug in upstream Rust wheels.

## Verifying the Release

- **PyPI**: https://pypi.org/project/forbin-mcp/
- **GitHub Release**: Check the Releases tab on the repo
- **Homebrew**: `brew update && brew upgrade forbin`

## Versioning

This project uses semantic versioning:

- **Patch** (0.1.x): Bug fixes, minor improvements
- **Minor** (0.x.0): New features, non-breaking changes
- **Major** (x.0.0): Breaking changes

## Troubleshooting

### Workflow not triggered
Ensure the tag matches the pattern `v[0-9]*.[0-9]*.[0-9]*` and was pushed to the remote.

### PyPI publish fails
Check that the `pypi` environment is configured in repo settings with trusted publisher (PyPA).

### Homebrew update fails
- Verify the `HOMEBREW_TAP_TOKEN` secret is set and not expired
- The token needs Contents read/write permission on `chris-colinsky/homebrew-forbin`
- The workflow waits 30 seconds for PyPI to index before fetching package info; if PyPI is slow, re-run the job

### Bottle build fails
- Check the `bottles.yml` run on `chris-colinsky/homebrew-forbin`
- A wheel-relocation error (`Failed changing dylib ID`) on a Rust extension means `RUSTFLAGS` didn't reach the compile step — verify `--no-binary :all:` is intact in both `release.yml` (this repo) and `Formula/forbin.rb` (tap repo).
- A relocation failure on a C (non-Rust) extension means a wheel needs a different linker flag than `RUSTFLAGS` provides; add a `CFLAGS`/`LDFLAGS` ENV append.
- Re-trigger by re-running the bottles workflow from the Actions tab, or pushing any change to `Formula/forbin.rb`.
