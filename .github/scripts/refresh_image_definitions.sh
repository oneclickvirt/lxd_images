#!/bin/bash
set -eo pipefail
source "$CI_IMAGE_SCRIPT_ROOT/ci_network.sh"
# from https://github.com/oneclickvirt/lxd_images
# Thanks https://images.lxd.canonical.com/
# 2025.08.19

BASE_URL="https://images.lxd.canonical.com/images"
CURRENT_DIR=$(pwd)
SAVE_DIR="$CURRENT_DIR/images_yaml"

mkdir -p "$SAVE_DIR"

check_remote_file_updated() {
    local remote_url="$1"
    local local_file="$2"
    
    if [ ! -f "$local_file" ]; then
        echo "true"
        return
    fi
    
    local remote_etag=$(curl -sI "$remote_url" | grep -i etag | cut -d' ' -f2- | tr -d '\r')
    local remote_lastmod=$(curl -sI "$remote_url" | grep -i last-modified | cut -d' ' -f2- | tr -d '\r')
    
    local meta_file="${local_file}.meta"
    if [ -f "$meta_file" ]; then
        local cached_etag=$(grep "^etag:" "$meta_file" 2>/dev/null | cut -d' ' -f2-)
        local cached_lastmod=$(grep "^last-modified:" "$meta_file" 2>/dev/null | cut -d' ' -f2-)
        
        if [ -n "$remote_etag" ] && [ -n "$cached_etag" ]; then
            if [ "$remote_etag" = "$cached_etag" ]; then
                echo "false"
                return
            fi
        elif [ -n "$remote_lastmod" ] && [ -n "$cached_lastmod" ]; then
            if [ "$remote_lastmod" = "$cached_lastmod" ]; then
                echo "false"
                return
            fi
        fi
    fi
    
    echo "true"
}

save_remote_metadata() {
    local remote_url="$1"
    local local_file="$2"
    local meta_file="${local_file}.meta"
    
    local headers=$(curl -sI "$remote_url")
    echo "$headers" | grep -i etag | sed 's/^[Ee][Tt][Aa][Gg]: */etag: /' > "$meta_file"
    echo "$headers" | grep -i last-modified | sed 's/^[Ll][Aa][Ss][Tt]-[Mm][Oo][Dd][Ii][Ff][Ii][Ee][Dd]: */last-modified: /' >> "$meta_file"
}

echo "Fetching images list..."
IMAGES_JSON=$(curl -s "https://images.lxd.canonical.com/streams/v1/images.json")

if [ -z "$IMAGES_JSON" ]; then
    echo "Failed to fetch images list."
    exit 1
fi

declare -A LATEST_YAML
declare -A FILES_TO_MODIFY

SYSTEMS="debian ubuntu kali centos almalinux rockylinux oracle archlinux fedora alpine openwrt opensuse openeuler gentoo"

for SYSTEM in $SYSTEMS; do
    echo "Processing: $SYSTEM"
    LATEST_VERSION=""
    LATEST_TIMESTAMP=""
    LATEST_PROFILE=""
    
    PRODUCT_KEYS=$(echo "$IMAGES_JSON" | grep -o "\"$SYSTEM:[^\"]*:amd64:[^\"]*\"" | sed 's/"//g')
    
    for PRODUCT_KEY in $PRODUCT_KEYS; do
        IFS=':' read -ra KEY_PARTS <<< "$PRODUCT_KEY"
        if [ ${#KEY_PARTS[@]} -eq 4 ]; then
            VERSION="${KEY_PARTS[1]}"
            VARIANT="${KEY_PARTS[3]}"
            
            VERSIONS_DATA=$(echo "$IMAGES_JSON" | jq -r ".products.\"$PRODUCT_KEY\".versions // {}" 2>/dev/null)
            if [ "$VERSIONS_DATA" != "{}" ] && [ "$VERSIONS_DATA" != "null" ]; then
                TIMESTAMPS=$(echo "$VERSIONS_DATA" | jq -r 'keys[]' 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{4}$')
                
                for TIMESTAMP in $TIMESTAMPS; do
                    if [ -n "$TIMESTAMP" ]; then
                        if [ -z "$LATEST_TIMESTAMP" ] || [[ "$TIMESTAMP" > "$LATEST_TIMESTAMP" ]]; then
                            LATEST_VERSION="$VERSION"
                            LATEST_TIMESTAMP="$TIMESTAMP"
                            LATEST_PROFILE="$VARIANT"
                        fi
                    fi
                done
            fi
        fi
    done
    
    if [ -n "$LATEST_VERSION" ] && [ -n "$LATEST_TIMESTAMP" ]; then
        YAML_URL="$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/$LATEST_PROFILE/$LATEST_TIMESTAMP/image.yaml"
        LATEST_YAML[$SYSTEM]="$YAML_URL"
        echo "Found: $SYSTEM -> $YAML_URL"
    else
        echo "No suitable image found for $SYSTEM"
    fi
done

echo "Found latest YAML files:"
for SYS in "${!LATEST_YAML[@]}"; do
    echo "$SYS -> ${LATEST_YAML[$SYS]}"
done

cd "$SAVE_DIR"

echo "Checking for updates..."
for SYS in "${!LATEST_YAML[@]}"; do
    YAML_FILE="$SYS.yaml"
    YAML_URL="${LATEST_YAML[$SYS]}"
    
    needs_update=$(check_remote_file_updated "$YAML_URL" "$YAML_FILE")
    
    if [ "$needs_update" = "true" ]; then
        echo "[$SYS] Remote file updated, will re-download and re-modify"
        FILES_TO_MODIFY[$SYS]="$YAML_URL"
        rm -f "${YAML_FILE}.modified"
    else
        echo "[$SYS] File is up-to-date, skipping"
    fi
done

echo "Downloading YAML files..."
for SYS in "${!LATEST_YAML[@]}"; do
    YAML_FILE="$SYS.yaml"
    YAML_URL="${LATEST_YAML[$SYS]}"
    
    if [[ -v FILES_TO_MODIFY[$SYS] ]]; then
        echo "Downloading from: $YAML_URL"
        if curl -s -o "$YAML_FILE" "$YAML_URL"; then
            if [ -s "$YAML_FILE" ]; then
                echo "Downloaded: $YAML_FILE"
                save_remote_metadata "$YAML_URL" "$YAML_FILE"
            else
                echo "Downloaded empty file, removing: $YAML_FILE"
                rm -f "$YAML_FILE" "${YAML_FILE}.meta"
            fi
        else
            echo "Failed to download: $YAML_URL"
        fi
    else
        echo "Skipped (already exists and up-to-date): $YAML_FILE"
    fi
done

patch_alpine_vm_boot() {
    local file_name="$1"
    if [ ! -f "$file_name" ]; then
        echo "Warning: $file_name not found for VM boot patching"
        return
    fi
    echo "Patching Alpine VM boot in $file_name"
    # Fix GRUB cmdline to include sd-mod and usb-storage modules for VM boot
    sed -i 's#GRUB_CMDLINE_LINUX_DEFAULT="console=tty1 console=ttyS0 modules={{ targets.lxd.vm.filesystem }} rootfstype={{ targets.lxd.vm.filesystem }}"#GRUB_CMDLINE_LINUX_DEFAULT="console=tty1 console=ttyS0 modules=sd-mod,usb-storage,{{ targets.lxd.vm.filesystem }} rootfstype={{ targets.lxd.vm.filesystem }}"#' "$file_name"
    # Add udev package for VM boot
    if ! grep -q '^    - udev$' "$file_name"; then
        sed -i '/    - linux-virt/a\    - udev' "$file_name"
    fi
    # Fix openrc services to include udev-related services
    sed -i 's#for svc_name in devfs dmesg hwdrivers mdev; do#for svc_name in devfs dmesg hwdrivers mdev udev udev-settle udev-trigger; do#' "$file_name"
    # Fix grub-install to use correct efi directory
    sed -i 's#grub-install --target=${TARGET}-efi --no-nvram --removable#grub-install --target=${TARGET}-efi --efi-directory=/boot/efi --no-nvram --removable#' "$file_name"
    sed -i 's#grub-install --target=${TARGET}-efi --no-nvram$#grub-install --target=${TARGET}-efi --efi-directory=/boot/efi --no-nvram#' "$file_name"
    # Add BOOT_EFI check after grub-install
    if ! grep -q 'BOOT_EFI="/boot/efi/EFI/BOOT/BOOTX64.EFI"' "$file_name"; then
        sed -i '/grub-install --target=${TARGET}-efi --efi-directory=\/boot\/efi --no-nvram$/a\    BOOT_EFI="/boot/efi/EFI/BOOT/BOOTX64.EFI"\n    [ "${TARGET}" = "arm64" ] \&\& BOOT_EFI="/boot/efi/EFI/BOOT/BOOTAA64.EFI"\n    test -s "${BOOT_EFI}"' "$file_name"
    fi
    # Fix rm to rm -f for safety
    sed -i 's#rm /etc/update-grub.conf#rm -f /etc/update-grub.conf#' "$file_name"
    echo "Alpine VM boot patched: $file_name"
}

modify_yaml_file() {
    local file_name="$1"
    local insert_point="$2"
    local packages="$3"
    local use_bash_insert="$4"
    if [ -f "${file_name}.modified" ]; then
        echo "Skipping ${file_name} - already modified"
        return
    fi
    if [ ! -f "$file_name" ]; then
        echo "Warning: $file_name not found"
        return
    fi
    echo "Modifying: $file_name"
    sed -i "/${insert_point}/ a\\${packages}" "$file_name"
    local hook="${CI_IMAGE_SCRIPT_ROOT}/../../sh_insert_content.text"
    if [ "$use_bash_insert" = "true" ]; then
        hook="${CI_IMAGE_SCRIPT_ROOT}/../../bash_insert_content.text"
    fi
    "$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "$file_name" "$hook"
    # if [[ "$file_name" == "almalinux.yaml" ]]; then
    #     sed -i 's|https://repo.almalinux.org/almalinux|https://almalinux.savoirfairelinux.net|g' "$file_name"
    # fi
    # if [[ "$file_name" == "opensuse.yaml" ]]; then
    #     sed -i '/downloader: opensuse-http/a\  url: https://mirrorcache-eu.opensuse.org/download' "$file_name"
    # fi
    if [[ "$file_name" == "fedora.yaml" ]]; then
        sed -i 's#systemd-machine-id-setup#[ -f /etc/machine-id ] || uuidgen > /etc/machine-id#g' "$file_name"
    fi
    touch "${file_name}.modified"
    echo "Modified: $file_name"
}

modify_yaml_file "debian.yaml" "- vim" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron" "true"

modify_yaml_file "ubuntu.yaml" "- vim" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron" "true"

modify_yaml_file "kali.yaml" "- systemd" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron" "true"

modify_yaml_file "centos.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "almalinux.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "rockylinux.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "oracle.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "archlinux.yaml" "- which" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix" "true"

modify_yaml_file "fedora.yaml" "- xz" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "alpine.yaml" "- doas" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - cronie\n    - iptables\n    - dos2unix" "false"
patch_alpine_vm_boot alpine.yaml

modify_yaml_file "openwrt.yaml" "- sudo" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables" "false"

modify_yaml_file "opensuse.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "openeuler.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "gentoo.yaml" "NOOP_NO_MATCH" "" "true"

cd "$CURRENT_DIR"
