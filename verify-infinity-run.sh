#!/usr/bin/env bash
# Infinity Agent QA + Run Verification Script
# This script runs QA checks and validates the Infinity Agent build and deployment

set -e

REPORT_FILE="report.log"
echo "=== Infinity Agent QA Verification ===" > "$REPORT_FILE"
echo "Timestamp: $(date)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

FAILED=0

# Function to log to both console and report file
log() {
    echo "$1" | tee -a "$REPORT_FILE"
}

# Step 1: Environment Check
log "Step 1: Checking environment variables..."
if [ -z "${VITE_HF_READ_TOKEN:-}" ] && [ -z "${VITE_HF_TOKEN:-}" ]; then
    log "⚠️  WARNING: Hugging Face token not set (VITE_HF_READ_TOKEN or VITE_HF_TOKEN)"
    log "   This is OK for local builds but will affect runtime connectivity checks"
else
    log "✅ Hugging Face token is set"
fi
log ""

# Step 2: Dependency Check
log "Step 2: Checking node_modules..."
if [ -d "node_modules" ]; then
    log "✅ Dependencies installed (node_modules exists)"
else
    log "❌ Dependencies not installed (node_modules missing)"
    FAILED=1
fi
log ""

# Step 3: Build Check
log "Step 3: Running production build..."
if npm run build > >(tee -a "$REPORT_FILE") 2>&1; then
    log "✅ Build succeeded"
else
    log "❌ Build failed"
    FAILED=1
fi
log ""

# Step 4: Dist Check
log "Step 4: Checking build output..."
if [ -d "dist" ] && [ -f "dist/index.html" ]; then
    log "✅ Build output exists (dist/index.html)"
else
    log "❌ Build output missing"
    FAILED=1
fi
log ""

# Step 5: Source Integrity Check
log "Step 5: Checking source integrity..."
if [ -f "src/App.jsx" ] && [ -f "src/main.jsx" ]; then
    log "✅ Source files present"
else
    log "❌ Source files missing"
    FAILED=1
fi
log ""

# Step 6: Package Scripts Check
log "Step 6: Checking package.json scripts..."
if grep -q '"build"' package.json && grep -q '"start"' package.json; then
    log "✅ Required scripts (build, start) defined"
else
    log "❌ Required scripts missing from package.json"
    FAILED=1
fi
log ""

# Step 7: Vite Configuration Check
log "Step 7: Checking Vite configuration..."
if [ -f "vite.config.js" ]; then
    log "✅ vite.config.js exists"
else
    log "⚠️  vite.config.js not found (may be optional)"
fi
log ""

# Step 8: Connectivity Check (if token available)
log "Step 8: Checking Hugging Face connectivity..."
if command -v curl >/dev/null 2>&1; then
    HF_TOKEN="${VITE_HF_READ_TOKEN:-${VITE_HF_TOKEN:-}}"
    if [ -n "$HF_TOKEN" ]; then
        if curl -s -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2 | grep -q "name"; then
            log "✅ Hugging Face API reachable"
        else
            log "⚠️  Hugging Face API not reachable (token may be read-only)"
        fi
    else
        log "ℹ️  Skipping HF connectivity check (no token)"
    fi
else
    log "ℹ️  Skipping HF connectivity check (curl not available)"
fi
log ""

# Summary
log "=== QA Verification Summary ==="
if [ $FAILED -eq 0 ]; then
    log "✅ All QA checks passed!"
    log ""
    echo ""
    echo "✅ QA verification complete. Report saved to $REPORT_FILE"
    echo ""
    exit 0
else
    log "❌ Some QA checks failed. Please review the report above."
    log ""
    echo ""
    echo "❌ QA verification failed. Please review $REPORT_FILE for details."
    echo ""
    exit 1
fi