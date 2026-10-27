# Meridian for iOS & macOS

A native multiplatform SwiftUI app (`apple/`) for **iPhone, iPad and Mac**.
Like the Android app in [`android/`](../android/README.md), the study workspace
works completely offline: the 93-subject / 406-topic catalogue, the full notes
for every topic at four depths, the 534-question practice bank with
explanations, study streaks, planner tasks, learning record and appearance
settings. Only the interactive diagrams, 3D models and the WebAssembly code
playground open the Meridian website inside a hardened `WKWebView`.

| | |
|---|---|
| Download | `Meridian-iOS.ipa` and `Meridian-macOS.dmg` from the [apple-latest release](https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/tag/apple-latest), rebuilt on every push |
| Bundle identifier | `io.github.sauravprivatelimited369byte.engineverse` |
| Platforms | iOS / iPadOS 17.0+ (`arm64`) and macOS 14.0 Sonoma+ (Universal `arm64` + `x86_64`) |
| Toolchain | Swift 5.10 / 6.0, SwiftUI + WebKit, Swift Package Manager (`Package.swift`) |
| Website it opens | `AppConfig.siteURL` (`https://sauravprivatelimited369-byte.github.io/Engine_Verse/`) |

## What is in the app

| Screen | Works offline | What it does |
|---|---|---|
| Home | Yes | Streak, topic completion and open planner counts, next task and quick actions |
| Learn | Yes | 93 subjects and 406 topics bundled in `Resources/catalog.json`, with group filters and multi-word search |
| Notes | Yes | All four note depths for every topic rendered natively from `Resources/content.json`: definitions, formulas, derivations, worked examples, exam and interview notes, tables and equations |
| Practice | Yes | The 534-question multiple-choice bank with explanations; answers are marked and kept on the device |
| Code playground | No | Opens CodeLab, the compilers and judged problems (WebAssembly workers) |
| Study planner | Yes | Tasks with optional due dates, overdue/today/upcoming badges, completion tracking |
| Learning record | Yes | Completed topics grouped by subject, with native `ShareLink` export |
| Settings | Yes | System / Light / Dark appearance, local-only data controls and Delete all app data |

On macOS and iPadOS (`regular` horizontal size class), navigation uses a native
`NavigationSplitView` sidebar; on iPhone (`compact`), it uses a native bottom
`TabView`.

## Privacy and WebView hardening

- **No accounts, analytics or tracking.** `Resources/PrivacyInfo.xcprivacy`
  declares `NSPrivacyTracking = false` and `NSPrivacyCollectedDataTypes = []`.
  Progress, streaks, planner tasks and theme live only in the app's local
  `UserDefaults` suite.
- **Restricted `WKWebView` (`WebViewerView.swift` + `UrlPolicy.swift`):**
  - Only HTTPS pages under `AppConfig.siteURL` load inside the app.
  - External `https://`, `http://` and `mailto:` links open in Safari or the
    user's default browser.
  - `javascript:`, `file:`, `data:`, `intent:` and path-traversal URLs are
    blocked.
  - `NSAllowsArbitraryLoads` is `false` on both iOS and macOS.
  - No `WKScriptMessageHandler` JavaScript bridge is registered, and automatic
    pop-up windows (`javaScriptCanOpenWindowsAutomatically = false`) are
    disabled.

## Build and test on macOS

Open `apple/Package.swift` in Xcode 16+, or build from the terminal:

```bash
# Regenerate or verify the offline catalogue and lesson library
python3 scripts/export_apple_catalog.py
python3 scripts/export_mobile_content.py          # writes Resources/content.json (and the Android copy)
python3 scripts/export_apple_catalog.py --check
python3 scripts/export_mobile_content.py --check

# Run Swift unit tests, build universal Meridian-macOS.dmg and Meridian-iOS.ipa
bash apple/scripts/build_apple.sh --all
```

Outputs are written to `apple/build/out/`:

- `Meridian-macOS.dmg` (+ `.sha256`) — Universal (`arm64` + `x86_64`) macOS disk image with `Meridian.app` and `/Applications` shortcut.
- `Meridian-iOS.ipa` (+ `.sha256`) — Native `arm64` iOS/iPadOS app package. Installable with AltStore, SideStore, Sideloadly or Xcode / Apple Configurator using a personal Apple ID, or directly when signed with an Apple Developer certificate and provisioning profile.

## CI and signing

[`.github/workflows/apple-build.yml`](../.github/workflows/apple-build.yml)
runs on `macos-15` to execute `swift test`, verify iOS Simulator compilation,
and build `Meridian-macOS.dmg` and `Meridian-iOS.ipa` (with SHA-256 digests).
Optional Apple Developer signing and notarization secrets (`APPLE_CERTIFICATE_BASE64`,
`APPLE_CERTIFICATE_PASSWORD`, `APPLE_MACOS_SIGN_IDENTITY`, `APPLE_IOS_SIGN_IDENTITY`,
`APPLE_IOS_PROVISION_PROFILE_BASE64`, `APPLE_NOTARY_APPLE_ID`,
`APPLE_NOTARY_TEAM_ID`, `APPLE_NOTARY_PASSWORD`) are read only from GitHub
Actions secrets when present and never committed.
