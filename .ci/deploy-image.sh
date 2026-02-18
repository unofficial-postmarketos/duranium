#!/bin/sh
set -e

IMAGE_ID="${DEVICE}_${UI}_${RELEASE}"

# Download existing manifest
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/SHA256SUMS" SHA256SUMS.old || touch SHA256SUMS.old
scp -P "$SSH_PORT" "$SSH_HOST:/var/www/duranium.postmarketos.org/images/$IMAGE_ID/SHA256SUMS.gpg" SHA256SUMS.old.gpg || true

# Verify existing manifest if signature exists
if [ -f SHA256SUMS.old.gpg ]; then gpg --verify SHA256SUMS.old.gpg SHA256SUMS.old; fi

# Prune old images, keeping (IMAGES_TO_KEEP - 1) old versions to make room for the new one
versions=$(grep " ${IMAGE_ID}_" SHA256SUMS.old | sed "s/.*${IMAGE_ID}_//" | cut -d. -f1 | sort -u)
if [ -n "$versions" ]; then
	total=$(echo "$versions" | wc -l)
	keep=$((IMAGES_TO_KEEP - 1))
	prune_count=$((total - keep))
	if [ $prune_count -gt 0 ]; then
		prune_versions=$(echo "$versions" | head -n $prune_count)
		for version in $prune_versions; do
			# collect files for this version from the manifest
			files=$(grep " ${IMAGE_ID}_${version}\." SHA256SUMS.old | awk '{print $2}')
			# delete from server
			for f in $files; do
				ssh -p "$SSH_PORT" "$SSH_HOST" "rm -f /var/www/duranium.postmarketos.org/images/$IMAGE_ID/$f"
			done
			# remove from manifest
			sed -i "/ ${IMAGE_ID}_${version}\./d" SHA256SUMS.old
		done
	fi
fi

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
