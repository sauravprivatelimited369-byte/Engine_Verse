#!/usr/bin/env bash
# Build, unit-test and package the native Meridian apps for macOS (.dmg) and iOS (.ipa).
# Requires macOS 14+ with Xcode 15.4+ / 16+. Secrets are never echoed or stored in the repo.
set -euo pipefail

APPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$APPLE_DIR/.." && pwd)"
OUT_DIR="${OUT_DIR:-$APPLE_DIR/build/out}"
WORK_DIR="$APPLE_DIR/build/work"
ICON_SRC="$REPO_ROOT/backend/static/icons/icon-512.png"

run_tests=false
run_macos=false
run_ios=false

if [ "$#" -eq 0 ]; then
  run_tests=true
  run_macos=true
  run_ios=true
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --test) run_tests=true ;;
    --macos) run_macos=true ;;
    --ios) run_ios=true ;;
    --all) run_tests=true; run_macos=true; run_ios=true ;;
    --out)
      shift
      OUT_DIR="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$OUT_DIR" "$WORK_DIR"
cd "$APPLE_DIR"

if [ ! -f "$APPLE_DIR/Resources/catalog.json" ]; then
  echo "error: apple/Resources/catalog.json is missing; run scripts/export_apple_catalog.py" >&2
  exit 1
fi
if [ ! -f "$APPLE_DIR/Resources/content.json" ]; then
  echo "error: apple/Resources/content.json is missing; run scripts/export_mobile_content.py" >&2
  exit 1
fi
if [ ! -f "$ICON_SRC" ]; then
  echo "error: icon source missing at $ICON_SRC" >&2
  exit 1
fi

if [ "$run_tests" = true ]; then
  echo "==> Running MeridianCore Swift unit tests"
  swift test
fi

build_macos_icns() {
  local dest_icns="$1"
  local iconset="$WORK_DIR/AppIcon.iconset"
  rm -rf "$iconset"
  mkdir -p "$iconset"
  sips -z 16 16     "$ICON_SRC" --out "$iconset/icon_16x16.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$iconset/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "$ICON_SRC" --out "$iconset/icon_32x32.png" >/dev/null
  sips -z 64 64     "$ICON_SRC" --out "$iconset/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "$ICON_SRC" --out "$iconset/icon_128x128.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$iconset/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$ICON_SRC" --out "$iconset/icon_256x256.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$iconset/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$ICON_SRC" --out "$iconset/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_SRC" --out "$iconset/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$iconset" -o "$dest_icns"
}

if [ "$run_macos" = true ]; then
  echo "==> Building universal macOS app (arm64 + x86_64)"
  swift build -c release --arch arm64 --arch x86_64 --product Meridian

  BIN="$APPLE_DIR/.build/apple/Products/Release/Meridian"
  if [ ! -f "$BIN" ]; then
    echo "error: expected universal binary at $BIN" >&2
    exit 1
  fi
  archs="$(lipo -archs "$BIN")"
  echo "    macOS binary architectures: $archs"
  case "$archs" in
    *arm64*x86_64*|*x86_64*arm64*) ;;
    *) echo "error: expected universal arm64+x86_64 binary, got: $archs" >&2; exit 1 ;;
  esac

  MAC_APP="$WORK_DIR/macos/Meridian.app"
  rm -rf "$WORK_DIR/macos" "$WORK_DIR/dmg_stage"
  mkdir -p "$MAC_APP/Contents/MacOS" "$MAC_APP/Contents/Resources"

  cp "$BIN" "$MAC_APP/Contents/MacOS/Meridian"
  chmod 0755 "$MAC_APP/Contents/MacOS/Meridian"
  cp "$APPLE_DIR/Resources/macOS/Info.plist" "$MAC_APP/Contents/Info.plist"
  cp "$APPLE_DIR/Resources/catalog.json" "$MAC_APP/Contents/Resources/catalog.json"
  cp "$APPLE_DIR/Resources/content.json" "$MAC_APP/Contents/Resources/content.json"
  cp "$APPLE_DIR/Resources/PrivacyInfo.xcprivacy" "$MAC_APP/Contents/Resources/PrivacyInfo.xcprivacy"
  printf 'APPL????' > "$MAC_APP/Contents/PkgInfo"
  build_macos_icns "$MAC_APP/Contents/Resources/AppIcon.icns"

  if [ -n "${MACOS_SIGN_IDENTITY:-}" ]; then
    codesign --force --deep --options runtime \
      --entitlements "$APPLE_DIR/Resources/macOS/Meridian.entitlements" \
      --sign "$MACOS_SIGN_IDENTITY" "$MAC_APP"
  else
    codesign --force --deep --sign - "$MAC_APP"
  fi
  codesign --verify --deep --strict "$MAC_APP"

  mkdir -p "$WORK_DIR/dmg_stage"
  cp -R "$MAC_APP" "$WORK_DIR/dmg_stage/Meridian.app"
  ln -s /Applications "$WORK_DIR/dmg_stage/Applications"

  DMG_PATH="$OUT_DIR/Meridian-macOS.dmg"
  rm -f "$DMG_PATH" "$DMG_PATH.sha256"
  dmg_ok=false
  for attempt in 1 2 3; do
    if hdiutil create -volname "Meridian" -srcfolder "$WORK_DIR/dmg_stage" -ov -format UDZO "$DMG_PATH" >/dev/null; then
      dmg_ok=true
      break
    fi
    sleep 2
  done
  if [ "$dmg_ok" != true ]; then
    echo "error: hdiutil failed to create $DMG_PATH" >&2
    exit 1
  fi
  hdiutil verify "$DMG_PATH" >/dev/null
  (cd "$OUT_DIR" && shasum -a 256 "Meridian-macOS.dmg" > "Meridian-macOS.dmg.sha256")
  echo "    Built $DMG_PATH ($(wc -c < "$DMG_PATH" | tr -d ' ') bytes)"
fi

compile_ios_slice() {
  local sdk="$1"
  local target="$2"
  local slice_dir="$3"
  local out_bin="$4"
  rm -rf "$slice_dir"
  mkdir -p "$slice_dir"

  xcrun --sdk "$sdk" swiftc \
    -target "$target" \
    -O -whole-module-optimization -swift-version 5 \
    -parse-as-library \
    -module-name MeridianCore \
    -emit-module -emit-module-path "$slice_dir/MeridianCore.swiftmodule" \
    -emit-library -static -o "$slice_dir/libMeridianCore.a" \
    "$APPLE_DIR"/Sources/MeridianCore/*.swift

  xcrun --sdk "$sdk" swiftc \
    -target "$target" \
    -O -whole-module-optimization -swift-version 5 \
    -parse-as-library \
    -module-name Meridian \
    -I "$slice_dir" -L "$slice_dir" -lMeridianCore \
    -o "$out_bin" \
    "$APPLE_DIR"/Sources/MeridianApp/*.swift
}

if [ "$run_ios" = true ]; then
  echo "==> Verifying iOS Simulator build (arm64-apple-ios17.0-simulator)"
  compile_ios_slice iphonesimulator "arm64-apple-ios17.0-simulator" \
    "$WORK_DIR/iossim" "$WORK_DIR/iossim/MeridianSim"

  echo "==> Building native iOS app (arm64-apple-ios17.0)"
  IPA_STAGE="$WORK_DIR/ios_ipa"
  IOS_APP="$IPA_STAGE/Payload/Meridian.app"
  rm -rf "$IPA_STAGE"
  mkdir -p "$IOS_APP"

  compile_ios_slice iphoneos "arm64-apple-ios17.0" \
    "$WORK_DIR/iphoneos" "$IOS_APP/Meridian"
  chmod 0755 "$IOS_APP/Meridian"

  ios_archs="$(lipo -archs "$IOS_APP/Meridian")"
  echo "    iOS binary architectures: $ios_archs"
  if [ "$ios_archs" != "arm64" ]; then
    echo "error: expected arm64 iOS binary, got: $ios_archs" >&2
    exit 1
  fi

  cp "$APPLE_DIR/Resources/iOS/Info.plist" "$IOS_APP/Info.plist"
  cp "$APPLE_DIR/Resources/catalog.json" "$IOS_APP/catalog.json"
  cp "$APPLE_DIR/Resources/content.json" "$IOS_APP/content.json"
  cp "$APPLE_DIR/Resources/PrivacyInfo.xcprivacy" "$IOS_APP/PrivacyInfo.xcprivacy"
  printf 'APPL????' > "$IOS_APP/PkgInfo"

  sips -z 120 120 "$ICON_SRC" --out "$IOS_APP/AppIcon60x60@2x.png" >/dev/null
  sips -z 180 180 "$ICON_SRC" --out "$IOS_APP/AppIcon60x60@3x.png" >/dev/null
  sips -z 152 152 "$ICON_SRC" --out "$IOS_APP/AppIcon76x76@2x~ipad.png" >/dev/null
  sips -z 167 167 "$ICON_SRC" --out "$IOS_APP/AppIcon83.5x83.5@2x~ipad.png" >/dev/null

  if [ -n "${IOS_PROVISION_PROFILE_PATH:-}" ] && [ -f "$IOS_PROVISION_PROFILE_PATH" ]; then
    cp "$IOS_PROVISION_PROFILE_PATH" "$IOS_APP/embedded.mobileprovision"
  fi

  if [ -n "${IOS_SIGN_IDENTITY:-}" ]; then
    codesign --force --entitlements "$APPLE_DIR/Resources/iOS/Meridian.entitlements" \
      --sign "$IOS_SIGN_IDENTITY" "$IOS_APP"
  else
    codesign --force --sign - "$IOS_APP"
  fi

  IPA_PATH="$OUT_DIR/Meridian-iOS.ipa"
  rm -f "$IPA_PATH" "$IPA_PATH.sha256"
  ditto -c -k --sequesterRsrc --keepParent "$IPA_STAGE/Payload" "$IPA_PATH"
  (cd "$OUT_DIR" && shasum -a 256 "Meridian-iOS.ipa" > "Meridian-iOS.ipa.sha256")
  echo "    Built $IPA_PATH ($(wc -c < "$IPA_PATH" | tr -d ' ') bytes)"
fi
