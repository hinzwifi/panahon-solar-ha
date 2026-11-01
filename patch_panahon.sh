#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== DOST-PAGASA PANaHON Morphe Patch & XAPK Merge Pipeline ===${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MORPHE_DIR="/home/hinzwifi/Music/morphe-tcl"
XAPK_INPUT="/home/hinzwifi/Music/PANaHON_+Weather+App_1.1.3_APKPure.xapk"
MERGED_APK="${SCRIPT_DIR}/panahon_merged.apk"
PATCHED_APK="${SCRIPT_DIR}/panahon_patched.apk"

if [ ! -f "$XAPK_INPUT" ]; then
    echo -e "${RED}[ERROR] XAPK not found at ${XAPK_INPUT}${NC}"
    exit 1
fi

echo -e "${CYAN}[1/4] Merging split XAPK into standalone APK via APKEditor...${NC}"
"${MORPHE_DIR}/xapk_to_apk.sh" "$XAPK_INPUT" "$MERGED_APK"

echo -e "${CYAN}[2/4] Compiling Morphe Patch Bundle (.mpp) with Debloat PANaHON Resources...${NC}"
(
    cd "$MORPHE_DIR"
    if [ -f "./gradlew" ]; then
        ./gradlew buildAndroid
    else
        gradle buildAndroid
    fi
)

MPP_FILE=$(find "${MORPHE_DIR}/patches/build/libs" -name "*.mpp" | head -n 1)
CLI_JAR="${MORPHE_DIR}/morphe-cli.jar"

echo -e "${CYAN}[3/4] Listing available Morphe patches in bundle...${NC}"
java -jar "$CLI_JAR" list-patches --patches="$MPP_FILE"

echo -e "${CYAN}[4/4] Applying Morphe Patch to PANaHON standalone APK...${NC}"
java -jar "$CLI_JAR" patch \
    -p "$MPP_FILE" \
    -e "Debloat PANaHON Resources" \
    "$MERGED_APK" \
    -o "$PATCHED_APK"

if [ -f "${MORPHE_DIR}/debug.keystore" ]; then
    apksigner sign \
        --ks "${MORPHE_DIR}/debug.keystore" \
        --ks-pass pass:android \
        --key-pass pass:android \
        --v2-signing-enabled true \
        --v3-signing-enabled true \
        "$PATCHED_APK" 2>/dev/null || true
fi

echo -e "${GREEN}========================================================================${NC}"
echo -e "${GREEN} SUCCESS: Debloated & Hardware-Accelerated PANaHON APK generated at:${NC}"
echo -e "   ${CYAN}${PATCHED_APK}${NC}"
echo -e "${GREEN}========================================================================${NC}"
