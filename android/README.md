# Meridian for Android

A native Android app written in Kotlin with Jetpack Compose. Everything a
student uses every day is built into the app and works without a connection:
the subject catalogue, the full notes for every topic at four depths, the
practice question bank with explanations, progress, streaks and the planner.
Only the interactive diagrams, 3D models and the WebAssembly code playground
open the Meridian website.

| | |
|---|---|
| Download | `Meridian.apk` from the [android-latest release](https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/tag/android-latest), rebuilt on every push |
| Package | `io.github.sauravprivatelimited369byte.engineverse` (debug builds add `.debug`) |
| Android | 7.0 (API 24) and newer; compiles against API 37, targets API 36 |
| Toolchain | AGP 9.4.1 (built-in Kotlin), Gradle 9.6.0 wrapper, Compose BOM 2026.09.00, Java 17 |
| Website it opens | `BuildConfig.SITE_URL`, the GitHub Pages copy of this repository |

## What is in the app

| Screen | Works offline | What it does |
|---|---|---|
| Home | Yes | Streak, progress counts, your next open planner task and shortcuts to daily practice and opportunities |
| Learn | Yes | 93 subjects and 406 topics bundled in `assets/catalog.json`, with search and filters. "Mark complete" is saved on the device. Topics not yet expert-reviewed are labelled as drafts. |
| Notes | Yes | All four note depths for every topic are rendered natively from `assets/content.json`: definitions, formulas, derivations, worked examples, exam and interview notes, tables and equations. No web page is involved. |
| Practice | Yes | The 534-question multiple-choice bank with an explanation for every answer. Answers are marked and kept on the device. |
| Playground | No | Opens the website's CodeLab and problem pages. Code runs in the browser engine (WebAssembly in a worker), not on a server. |
| Planner | Yes | Tasks with optional due dates; overdue, today and upcoming groups |
| Portfolio | Yes | Completed topics by subject; "Share summary" uses the Android share sheet |
| Settings | Yes | Light, dark or system theme, links to the privacy policy and source, and "Delete all app data" |

System Back walks back through web pages first, then through screens. When a
page cannot load, a native offline screen offers a retry or the offline
catalogue.

### Data and privacy

There are no accounts, analytics or ads. Progress, streak days, planner tasks
and the theme live in one private SharedPreferences file (`engineverse.xml`).
Only that file is included in the user's own Android backup; WebView data is
not. The app asks for two permissions: `INTERNET` and `ACCESS_NETWORK_STATE`.
App progress is separate from the website's progress, which the website keeps
in its own storage.

### The web viewer

`ui/WebViewerScreen.kt` and `core/UrlPolicy.kt`:

- It loads only HTTPS pages under the site URL. Other links, such as YouTube or
  GitHub, open in the user's browser. `javascript:`, `file:`, `data:` and
  `intent:` URLs are blocked.
- Cleartext traffic is off (`network_security_config.xml`), mixed content is
  never allowed, file and content access are off, and Safe Browsing is on
  (API 26 and newer).
- It adds no `addJavascriptInterface` bridge, opens no pop-up windows and
  disables geolocation.
- File inputs, such as importing a progress file, open the system file picker.

Known limits: the website's "download" and "export" buttons cannot save files
inside the viewer, because they create blob URLs. Those buttons say so and
suggest **Open in browser** (top right). TLS errors are never bypassed: a page
with a certificate problem does not load.

## Build

You need JDK 17 and the Android SDK (platform 37). Android Studio provides both;
open the `android/` folder.

```bash
cd android
./gradlew testDebugUnitTest   # JVM unit tests (URL policy, streaks, planner, search)
./gradlew lintDebug           # Android lint; errors fail the build
./gradlew assembleDebug       # app/build/outputs/apk/debug/app-debug.apk
```

`./gradlew installDebug` installs on a connected device or emulator.

The bundled catalogue and lesson library are generated from the website's seed
data. After changing subjects, topics or notes, regenerate both from the
repository root:

```bash
python scripts/export_android_catalog.py          # rewrites assets/catalog.json
python scripts/export_mobile_content.py           # rewrites assets/content.json (and the Apple copy)
python scripts/export_android_catalog.py --check  # CI: fails if a file is stale
python scripts/export_mobile_content.py --check
```

`content.json` is Markdown already parsed into blocks and runs (see the
exporter's docstring), so the app never parses Markdown or loads a web page to
read a note.

`backend/tests/test_android_project.py` also checks that the catalogue matches
the seed data and that every page the app opens exists on the site.

## CI

[`.github/workflows/android-build.yml`](../.github/workflows/android-build.yml)
runs on every push and pull request that touches `android/`:

1. Ensures Android SDK platform 37 is installed, validates the Gradle wrapper, then runs the unit tests, lint and `assembleDebug`.
2. Uploads **engineverse-debug-apk**, the debug-signed APK and its SHA-256, and
   **engineverse-android-reports**, the test and lint reports, as workflow
   artifacts. Download them from the run page while signed in to GitHub.
3. Writes the unit-test totals, lint findings and the APK digest to the run
   summary.
4. On a push, attaches `Meridian.apk` and its SHA-256 to the rolling
   [android-latest](https://github.com/sauravprivatelimited369-byte/Engine_Verse/releases/tag/android-latest)
   release, so the APK can be downloaded and installed without a GitHub login.

The debug APK is for testing. It is signed with a throwaway debug key and is
not a store release.

## Signed release builds

Nothing secret is stored in this repository. `app/build.gradle.kts` reads the
signing configuration from four environment variables and builds an unsigned
release if any of them is missing:

| Variable | Meaning |
|---|---|
| `ENGINEVERSE_KEYSTORE_FILE` | Path to the upload keystore (`.jks`) |
| `ENGINEVERSE_KEYSTORE_PASSWORD` | Keystore password |
| `ENGINEVERSE_KEY_ALIAS` | Key alias |
| `ENGINEVERSE_KEY_PASSWORD` | Key password |

To publish from CI, a maintainer:

1. Creates a keystore once on their own machine and keeps a backup offline:
   `keytool -genkeypair -v -keystore engineverse-release.jks -keyalg RSA -keysize 4096 -validity 10000 -alias engineverse`
2. Adds these repository secrets (Settings > Secrets and variables > Actions):
   `ANDROID_KEYSTORE_BASE64` (the output of `base64 -w0 engineverse-release.jks`),
   `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`.
3. Runs **Android app** manually (Actions > Android app > Run workflow) with
   **release** ticked and a version such as `v1.0.0`.

The release job decodes the keystore into the runner's temporary directory,
builds a minified release, checks it with `apksigner verify`, and attaches
`Meridian.apk` and its `.sha256` to a GitHub Release named `android-<version>`.
Without the secrets it stops with an error and publishes nothing. Raise
`versionCode` in `app/build.gradle.kts` for every published release.

`*.jks`, `*.keystore` and `local.properties` are git-ignored. Never commit them.

## Self-hosting alternative: a TWA

`build-twa.cjs` (with `package.json`) is the older Trusted Web Activity
builder, kept for operators who run the full website on their own domain. A TWA
needs `/.well-known/assetlinks.json` at the root of that domain, which a GitHub
Pages project site cannot serve. See [docs/ANDROID_TWA.md](../docs/ANDROID_TWA.md).
It is not used by the native app or its CI.

`listing/` holds the store listing text and graphics.
