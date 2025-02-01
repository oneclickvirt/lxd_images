#!/bin/bash
# from https://github.com/oneclickvirt/lxd_images
# Thanks https://images.lxd.canonical.com/
# 2025.01.31

BASE_URL="https://images.lxd.canonical.com/images"
SAVE_DIR="/home/runner/work/lxd_images/lxd_images/images_yaml"
# 获取系统列表
echo "Fetching system list..."
SYSTEMS=$(curl -s "$BASE_URL/" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::')
declare -A LATEST_YAML
for SYSTEM in $SYSTEMS; do
    echo "Processing: $SYSTEM"
    VERSIONS=$(curl -s "$BASE_URL/$SYSTEM/" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::')
    LATEST_VERSION=$(echo "$VERSIONS" | sort -V | tail -n1)
    if [ -n "$LATEST_VERSION" ]; then
        ARCHES=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::')
        if echo "$ARCHES" | grep -q '^amd64$'; then
            PROFILES=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::')
            if echo "$PROFILES" | grep -q '^default$'; then
                PROFILE="default"
            elif echo "$PROFILES" | grep -q '^cloud$'; then
                PROFILE="cloud"
            else
                PROFILE=$(echo "$PROFILES" | sort -V | tail -n1)  # 选最后一个
            fi
            if [ -n "$PROFILE" ]; then
                DATES=$(curl -s "$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/$PROFILE/" | grep -oP '(?<=href=")[^"]+' | grep '/$' | sed 's:/$::')
                LATEST_DATE=$(echo "$DATES" | sort -V | tail -n1)
                YAML_URL="$BASE_URL/$SYSTEM/$LATEST_VERSION/amd64/$PROFILE/$LATEST_DATE/image.yaml"
                LATEST_YAML[$SYSTEM]="$YAML_URL"
            fi
        fi
    fi
done
echo "Found latest YAML files:"
for SYS in "${!LATEST_YAML[@]}"; do
    echo "$SYS -> ${LATEST_YAML[$SYS]}"
done
echo "Downloading YAML files..."
for SYS in "${!LATEST_YAML[@]}"; do
    YAML_FILE="$SAVE_DIR/$SYS.yaml"
    curl -s -o "$YAML_FILE" "${LATEST_YAML[$SYS]}"
    echo "Downloaded: $YAML_FILE"
done
echo "All YAML files downloaded successfully."

cd /home/runner/work/lxd_images/lxd_images/images_yaml/
# debian
chmod 777 debian.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" debian.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
line_number=$(($(wc -l < debian.yaml) - 2))
head -n $line_number debian.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 debian.yaml >> temp.yaml
mv temp.yaml debian.yaml
sed -i -e '/mappings:/i \ ' debian.yaml

# ubuntu
chmod 777 ubuntu.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" ubuntu.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
line_number=$(($(wc -l < ubuntu.yaml) - 2))
head -n $line_number ubuntu.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 ubuntu.yaml >> temp.yaml
mv temp.yaml ubuntu.yaml
sed -i -e '/mappings:/i \ ' ubuntu.yaml

# kali
chmod 777 kali.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- systemd/ a\\$insert_content_1" kali.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
line_number=$(($(wc -l < kali.yaml) - 2))
head -n $line_number kali.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 kali.yaml >> temp.yaml
mv temp.yaml kali.yaml
sed -i -e '/mappings:/i \ ' kali.yaml

# centos
chmod 777 centos.yaml
# epel-relase 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" centos.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat centos.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml centos.yaml

# almalinux
chmod 777 almalinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" almalinux.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat almalinux.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml almalinux.yaml

# rockylinux
chmod 777 rockylinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" rockylinux.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat rockylinux.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml rockylinux.yaml

# oracle
chmod 777 oracle.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" oracle.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat oracle.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml oracle.yaml

# archlinux
chmod 777 archlinux.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
sed -i "/- which/ a\\$insert_content_1" archlinux.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
line_number=$(($(wc -l < archlinux.yaml) - 2))
head -n $line_number archlinux.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 archlinux.yaml >> temp.yaml
mv temp.yaml archlinux.yaml
sed -i -e '/mappings:/i \ ' archlinux.yaml

# # gentoo
# chmod 777 gentoo.yaml
# # cronie 不可用 cron 不可用
# insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
# sed -i "/- sudo/ a\\$insert_content_1" gentoo.yaml
# insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
# line_number=$(($(wc -l < gentoo.yaml) - 3))
# head -n $line_number gentoo.yaml > temp.yaml
# echo "$insert_content_2" >> temp.yaml
# tail -n 3 gentoo.yaml >> temp.yaml
# mv temp.yaml gentoo.yaml
# sed -i -e '/environment:/i \ ' gentoo.yaml
# sed -i 's/- default/- openrc/g' gentoo.yaml

# fedora
chmod 777 fedora.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- xz/ a\\$insert_content_1" fedora.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat fedora.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml fedora.yaml

# alpine
chmod 777 alpine.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - cronie\n    - iptables\n    - dos2unix"
sed -i "/- doas/ a\\$insert_content_1" alpine.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/sh_insert_content.text)
line_number=$(($(wc -l < alpine.yaml) - 2))
head -n $line_number alpine.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 alpine.yaml >> temp.yaml
mv temp.yaml alpine.yaml
sed -i -e '/mappings:/i \ ' alpine.yaml

# openwrt
chmod 777 openwrt.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables"
sed -i "/- sudo/ a\\$insert_content_1" openwrt.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/sh_insert_content.text)
cat openwrt.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml openwrt.yaml

# opensuse
chmod 777 opensuse.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" opensuse.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat opensuse.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml opensuse.yaml

# openeuler
chmod 777 openeuler.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" openeuler.yaml
insert_content_2=$(cat /home/runner/work/lxd_images/lxd_images/bash_insert_content.text)
cat openeuler.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml openeuler.yaml

cd /home/runner/work/lxd_images/lxd_images

build_or_list_images() {
    local versions=()
    local ver_nums=()
    local variants=()
    read -ra versions <<< "$1"
    read -ra ver_nums <<< "$2"
    read -ra variants <<< "$3"
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
                        echo "${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip" >> x86_64_all_images.txt
                    elif [[ "$arch" == "aarch64" || "$arch" == "arm64" ]]; then
                        echo "${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip" >> arm64_all_images.txt
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
    # 如果文件不存在，则创建空文件
    if [ ! -f "$file" ]; then
        touch "$file"
    else
        # 删除重复行
        awk '!seen[$0]++' "$file" > temp && mv temp "$file"
        # 删除空行
        sed -i '/^$/d' "$file"
    fi
}

# 不同发行版的配置
# build_or_list_images 镜像名字 镜像版本号 variants的值
arch_list=("x86_64" "arm64")
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
