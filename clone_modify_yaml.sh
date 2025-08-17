#!/bin/bash
# from https://github.com/oneclickvirt/lxd_images
# Thanks https://images.lxd.canonical.com/
# 2025.08.17

BASE_URL="https://images.lxd.canonical.com/images"
CURRENT_DIR=$(pwd)
SAVE_DIR="$CURRENT_DIR/images_yaml"

mkdir -p "$SAVE_DIR"

parse_links() {
    local html_content="$1"
    echo "$html_content" | grep -oP '(?<=<a href=")[^"]+(?=">)' | grep '/$' | sed 's:/$::' | sort -u
    if [ ${PIPESTATUS[0]} -ne 0 ] || [ -z "$(echo "$html_content" | grep -oP '(?<=<a href=")[^"]+(?=">)' | grep '/$')" ]; then
        echo "$html_content" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::' | sort -u
    fi
}

echo "Fetching system list..."
SYSTEMS_HTML=$(curl -s "$BASE_URL/")
SYSTEMS=$(parse_links "$SYSTEMS_HTML")
declare -A LATEST_YAML

if [ -z "$SYSTEMS" ]; then
    echo "Failed to fetch systems list. Trying direct system names..."
    SYSTEMS="debian ubuntu kali centos almalinux rockylinux oracle archlinux fedora alpine openwrt opensuse openeuler gentoo"
fi

for SYSTEM in $SYSTEMS; do
    echo "Processing: $SYSTEM"
    VERSIONS_HTML=$(curl -s "$BASE_URL/$SYSTEM/")
    VERSIONS=$(parse_links "$VERSIONS_HTML")
    LATEST_VERSION=$(echo "$VERSIONS" | sort -V | tail -n1)
    if [ -n "$LATEST_VERSION" ]; then
        ARCHES_HTML=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/")
        ARCHES=$(parse_links "$ARCHES_HTML")
        if echo "$ARCHES" | grep -q '^amd64$'; then
            PROFILES_HTML=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/")
            PROFILES=$(parse_links "$PROFILES_HTML")
            if echo "$PROFILES" | grep -q '^default$'; then
                PROFILE="default"
            elif echo "$PROFILES" | grep -q '^cloud$'; then
                PROFILE="cloud"
            else
                PROFILE=$(echo "$PROFILES" | sort -V | tail -n1)
            fi
            if [ -n "$PROFILE" ]; then
                DATES_HTML=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/$PROFILE/")
                DATES=$(parse_links "$DATES_HTML")
                LATEST_DATE=$(echo "$DATES" | sort -V | tail -n1)
                if [ -n "$LATEST_DATE" ]; then
                    YAML_URL="$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/$PROFILE/$LATEST_DATE/image.yaml"
                    LATEST_YAML[$SYSTEM]="$YAML_URL"
                    echo "Found: $SYSTEM -> $YAML_URL"
                else
                    echo "No dates found for $SYSTEM"
                fi
            else
                echo "No profiles found for $SYSTEM"
            fi
        else
            echo "No amd64 architecture found for $SYSTEM"
        fi
    else
        echo "No versions found for $SYSTEM"
    fi
done

echo "Found latest YAML files:"
for SYS in "${!LATEST_YAML[@]}"; do
    echo "$SYS -> ${LATEST_YAML[$SYS]}"
done

echo "Downloading YAML files..."
for SYS in "${!LATEST_YAML[@]}"; do
    YAML_FILE="$SAVE_DIR/$SYS.yaml"
    YAML_URL="${LATEST_YAML[$SYS]}"
    if [ ! -f "$YAML_FILE" ] || [ ! -f "$YAML_FILE.modified" ]; then
        echo "Downloading from: $YAML_URL"
        if curl -s -o "$YAML_FILE" "$YAML_URL"; then
            if [ -s "$YAML_FILE" ]; then
                echo "Downloaded: $YAML_FILE"
            else
                echo "Downloaded empty file, removing: $YAML_FILE"
                rm -f "$YAML_FILE"
            fi
        else
            echo "Failed to download: $YAML_URL"
        fi
    else
        echo "Skipped (already exists and modified): $YAML_FILE"
    fi
done

cd "$SAVE_DIR"

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
    chmod 777 "$file_name"
    
    sed -i "/${insert_point}/ a\\${packages}" "$file_name"
    
    if [ "$use_bash_insert" = "true" ]; then
        insert_content_2=$(cat "$CURRENT_DIR/bash_insert_content.text" 2>/dev/null || echo "# bash_insert_content.text not found")
        if grep -q "mappings:" "$file_name"; then
            line_number=$(($(wc -l <"$file_name") - 2))
            head -n $line_number "$file_name" >temp.yaml
            echo "$insert_content_2" >>temp.yaml
            tail -n 2 "$file_name" >>temp.yaml
            mv temp.yaml "$file_name"
            sed -i -e '/mappings:/i \ ' "$file_name"
        else
            cat "$file_name" >temp.yaml
            echo "" >>temp.yaml
            echo "$insert_content_2" >>temp.yaml
            mv temp.yaml "$file_name"
        fi
    else
        insert_content_2=$(cat "$CURRENT_DIR/sh_insert_content.text" 2>/dev/null || echo "# sh_insert_content.text not found")
        if grep -q "mappings:" "$file_name"; then
            line_number=$(($(wc -l <"$file_name") - 2))
            head -n $line_number "$file_name" >temp.yaml
            echo "$insert_content_2" >>temp.yaml
            tail -n 2 "$file_name" >>temp.yaml
            mv temp.yaml "$file_name"
            sed -i -e '/mappings:/i \ ' "$file_name"
        else
            cat "$file_name" >temp.yaml
            echo "$insert_content_2" >>temp.yaml
            mv temp.yaml "$file_name"
        fi
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

modify_yaml_file "openwrt.yaml" "- sudo" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables" "false"

modify_yaml_file "opensuse.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

modify_yaml_file "openeuler.yaml" "- vim-minimal" "    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie" "true"

cd "$CURRENT_DIR"

build_or_list_images() {
    local versions=()
    local ver_nums=()
    local variants=()
    read -ra versions <<<"$1"
    read -ra ver_nums <<<"$2"
    read -ra variants <<<"$3"
    local architectures=("$build_arch")
    local len=${#versions[@]}
    for ((i = 0; i < len; i++)); do
        version=${versions[i]}
        ver_num=${ver_nums[i]}
        for arch in "${architectures[@]}"; do
            for variant in "${variants[@]}"; do
                local url="https://github.com/oneclickvirt/lxd_images/releases/download/${run_funct}/${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip"
                if curl --output /dev/null --silent --head --fail "$url"; then
                    if [[ "$arch" == "x86_64" || "$arch" == "amd64" ]]; then
                        echo "${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip" >>x86_64_all_images.txt
                    elif [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
                        echo "${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip" >>arm64_all_images.txt
                    fi
                else
                    echo "File not found: $url"
                fi
            done
        done
    done
}

get_versions() {
    local system=$1
    local url="https://images.lxd.canonical.com/images/$system/"
    versions=$(curl -s "$url" | grep -oE '>[0-9]+\.[0-9]+/?<' | sed 's/[><]//g' | sed 's#/$##' | tr '\n' ' ')
    echo "$versions"
}

remove_duplicate_lines() {
    sed -i 's/[ \t]*$//' "$1"
    if [ -f "$1" ]; then
        awk '{ line = $0; gsub(/^[ \t]+/, "", line); gsub(/[ \t]+/, " ", line); if (!NF || !seen[line]++) print $0 }' "$1" >"$1.tmp" && mv -f "$1.tmp" "$1"
    fi
}

process_file() {
    local file="$1"
    if [ ! -f "$file" ]; then
        touch "$file"
    else
        awk '!seen[$0]++' "$file" >temp && mv temp "$file"
        sed -i '/^$/d' "$file"
    fi
}

arch_list=("amd64" "arm64")
for build_arch in "${arch_list[@]}"; do
    echo "当前架构: $build_arch"
    run_funct="debian"
    build_or_list_images "buster bullseye bookworm trixie" "10 11 12 13" "default cloud"
    run_funct="ubuntu"
    build_or_list_images "bionic focal jammy lunar mantic noble" "18.04 20.04 22.04 23.04 23.10 24.04" "default cloud"
    run_funct="kali"
    build_or_list_images "kali-rolling" "latest" "default cloud"
    run_funct="archlinux"
    build_or_list_images "current" "current" "default cloud"
    run_funct="gentoo"
    build_or_list_images "current" "current" "cloud systemd openrc"
    run_funct="centos"
    build_or_list_images "7 8-Stream 9-Stream" "7 8 9" "default cloud"
    for system in almalinux rockylinux alpine openwrt oracle fedora opensuse openeuler; do
        versions=$(get_versions "$system")
        build_or_list_images "$versions" "$versions" "default cloud"
    done
done
process_file "x86_64_all_images.txt"
process_file "arm64_all_images.txt"

echo "All tasks completed successfully."
