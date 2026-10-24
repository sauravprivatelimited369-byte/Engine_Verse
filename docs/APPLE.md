# iOS & macOS distribution (`apple/`)

Meridian ships a native multiplatform SwiftUI project in [`apple/`](../apple/README.md)
targeting **macOS 14 Sonoma+** (Universal `arm64` + `x86_64`) and **iOS /
iPadOS 17+** (`arm64`), alongside Safari Web App installation.

## Packages built by CI

[`.github/workflows/apple-build.yml`](../.github/workflows/apple-build.yml)
runs on `macos-15` to:

1. Verify `apple/Resources/catalog.json` matches the seeded curriculum (`scripts/export_apple_catalog.py --check`).
2. Run Swift unit tests (`swift test` on `MeridianCoreTests`).
3. Verify `iphonesimulator` (`arm64-apple-ios17.0-simulator`) compilation.
4. Build and sign a Universal macOS `.app` inside `Meridian-macOS.dmg` (+ `.sha256`).
5. Build and sign a native `arm64` iOS `.app` inside `Meridian-iOS.ipa` (+ `.sha256`).
6. Verify binary headers (`koly` UDIF trailer, 64-bit Mach-O magic, `Info.plist`, bundled `catalog.json` and SHA-256 digests) with `scripts/verify_apple_release.py --local-dir apple/build/out`.

## How the website links to macOS and iOS downloads

`backend/engineverse/distribution.py` enforces strict URL allowlists so caller-controlled or unowned binary URLs are never advertised:

- `ENGINEVERSE_MACOS_URL`: must point to a versioned `Meridian*.dmg`/`.pkg`/`.zip` asset in *this* repository's GitHub Releases (`v*`, `apple-v*` or `macos-v*`).
- `ENGINEVERSE_IOS_URL`: must point to a versioned `Meridian*.ipa` asset in *this* repository's GitHub Releases (`v*`, `apple-v*` or `ios-v*`), or an official `https://testflight.apple.com/join/...` or `https://apps.apple.com/.../app/.../id...` listing.
- Local verified builds: when `data/releases/Meridian-macOS.dmg` or `data/releases/Meridian-iOS.ipa` is present on a host (or fetched during `pages.yml`), `/downloads/Meridian-macOS.dmg` and `/downloads/Meridian-iOS.ipa` (plus `.sha256` sidecars) are served directly with `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment`.

## Optional Apple Developer signing & notarization

Without Apple Developer secrets configured, CI produces ad-hoc signed packages (`codesign --sign -`):
- On macOS, learners open `Meridian-macOS.dmg`, drag `Meridian.app` to `Applications`, and Control-click → **Open** on first launch.
- On iOS/iPadOS, learners either sideload `Meridian-iOS.ipa` with **AltStore**, **SideStore**, **Sideloadly** or **Apple Configurator 2** using their Apple ID, or install the full-screen Web App directly from **Safari → Share → Add to Home Screen**.

To sign with an Apple Developer certificate and notarize macOS builds, add these repository **Secrets** (never variables or committed files):

- `APPLE_CERTIFICATE_BASE64` — base64-encoded `.p12` signing certificate
- `APPLE_CERTIFICATE_PASSWORD` — password for the `.p12` archive
- `APPLE_MACOS_SIGN_IDENTITY` — e.g. `Developer ID Application: ...`
- `APPLE_IOS_SIGN_IDENTITY` — e.g. `Apple Distribution: ...`
- `APPLE_IOS_PROVISION_PROFILE_BASE64` — base64-encoded `.mobileprovision`
- `APPLE_NOTARY_APPLE_ID`, `APPLE_NOTARY_TEAM_ID`, `APPLE_NOTARY_PASSWORD` — app-specific credentials for `xcrun notarytool`
