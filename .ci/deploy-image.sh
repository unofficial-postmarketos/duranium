#!/bin/sh
set -e

IMAGE_ID="${DEVICE}_${UI}_${RELEASE}"

# Download existing manifest
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/SHA256SUMS" SHA256SUMS.old || touch SHA256SUMS.old
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/SHA256SUMS.gpg" SHA256SUMS.old.gpg || true

# Verify existing manifest if signature exists
if [ -f SHA256SUMS.old.gpg ]; then gpg --verify SHA256SUMS.old.gpg SHA256SUMS.old; fi

# Merge manifests
mv mkosi.output/*/SHA256SUMS SHA256SUMS.new
cat SHA256SUMS.new SHA256SUMS.old > SHA256SUMS

# Sign manifest
gpg --detach-sign --armor -o SHA256SUMS.gpg SHA256SUMS

# Create remote directory
ssh -p "$SSH_PORT" "$SSH_HOST" "mkdir -p /var/www/duranium.postmarketos.org/images/$IMAGE_ID"

# Upload images
rsync -hrvz -e "ssh -p $SSH_PORT" mkosi.output/*/"${IMAGE_ID}"_*.* "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/"

# Upload version and manifest
rsync -hrvz -e "ssh -p $SSH_PORT" mkosi.version SHA256SUMS SHA256SUMS.gpg "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/"
