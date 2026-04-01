#!/bin/sh
#
# Expected enviroment variables:
#   DEPLOY_DIR: directory on the remote server to send the image to
#   ARTIFACT_PREFIX: portion of the artifact filename before the version
# Optional environment variables:
#   DEVICE: device, e.g. fairphone-fp5
#   UI: ui, e.g. phosh
#   RELEASE: release, e.g. edge
#
set -e

# Download existing manifest
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/SHA256SUMS" SHA256SUMS.old || touch SHA256SUMS.old
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/SHA256SUMS.gpg" SHA256SUMS.old.gpg || true

# Verify existing manifest if signature exists
if [ -f SHA256SUMS.old.gpg ]; then gpg --verify SHA256SUMS.old.gpg SHA256SUMS.old; fi

# Prune old images, keeping (IMAGES_TO_KEEP - 1) old versions to make room for the new one
versions=$(grep " ${ARTIFACT_PREFIX}_" SHA256SUMS.old | sed "s/.*${ARTIFACT_PREFIX}_//" | cut -d. -f1 | sort -u)
if [ -n "$versions" ]; then
	total=$(echo "$versions" | wc -l)
	keep=$((IMAGES_TO_KEEP - 1))
	prune_count=$((total - keep))
	if [ $prune_count -gt 0 ]; then
		prune_versions=$(echo "$versions" | head -n $prune_count)
		for version in $prune_versions; do
			# collect files for this version from the manifest
			files=$(grep " ${ARTIFACT_PREFIX}_${version}\." SHA256SUMS.old | awk '{print $2}')
			# delete from server
			for f in $files; do
				ssh -p "$SSH_PORT" "$SSH_HOST" "rm -f /var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/$f"
			done
			# remove from manifest
			sed -i "/ ${ARTIFACT_PREFIX}_${version}\./d" SHA256SUMS.old
		done
	fi
fi

# Merge manifests
mv mkosi.output/*/SHA256SUMS SHA256SUMS.new
cat SHA256SUMS.new SHA256SUMS.old > SHA256SUMS

# Sign manifest
gpg --detach-sign --armor -o SHA256SUMS.gpg SHA256SUMS

# Create remote directory
ssh -p "$SSH_PORT" "$SSH_HOST" "mkdir -p /var/www/duranium.postmarketos.org/images/$DEPLOY_DIR"

# Upload images
rsync -hrvz -e "ssh -p $SSH_PORT" mkosi.output/*/"${ARTIFACT_PREFIX}"_*.* "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/"

# Upload manifest
rsync -hrvz -e "ssh -p $SSH_PORT" SHA256SUMS SHA256SUMS.gpg "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/"

# Generate and upload latest.json (OS images only)
if [ -n "$DEVICE" ]; then
	IMAGE_ID="${DEVICE}_${UI}_${RELEASE}"
	version=$(cat mkosi.version)
	raw_file="${IMAGE_ID}_${version}.raw.zst"
	sha256=$(grep "  ${IMAGE_ID}_${version}\.raw\.zst$" SHA256SUMS.new | awk '{print $1}')
	cat > latest.json <<EOF
{
  "device": "$DEVICE",
  "ui": "$UI",
  "release": "$RELEASE",
  "version": "$version",
  "filename": "$raw_file",
  "sha256": "$sha256"
}
EOF
	rsync -hrvz -e "ssh -p $SSH_PORT" latest.json "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$DEPLOY_DIR/"
fi
