#!/usr/bin/env bash
# Rebuild (and optionally install) the Cloud Calculator Android TWA.
#   ./android/build_android.sh            -> build signed APK + AAB
#   ./android/build_android.sh --bump     -> increase version code first (needed for each Play upload)
#   ./android/build_android.sh --install  -> build, then install APK on a USB-connected phone
set -e
cd "$(dirname "$0")"
TOOLS="$HOME/android-tools"
BW="$TOOLS/bw/node_modules/.bin/bubblewrap"
export JAVA_HOME="$TOOLS/jdk" ANDROID_HOME="$TOOLS/sdk"

PW=$(grep "Store password" signing-key-info.txt | awk '{print $3}')
export BUBBLEWRAP_KEYSTORE_PASSWORD="$PW" BUBBLEWRAP_KEY_PASSWORD="$PW"

if [[ " $* " == *" --bump "* ]]; then
  "$BW" update            # bumps appVersionCode in twa-manifest.json
else
  "$BW" update --skipVersionUpgrade
fi
"$BW" build --skipPwaValidation

if [[ " $* " == *" --install "* ]]; then
  "$ANDROID_HOME/platform-tools/adb" install -r app-release-signed.apk
fi
echo "Outputs: $(pwd)/app-release-signed.apk  $(pwd)/app-release-bundle.aab"
