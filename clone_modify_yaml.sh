#!/bin/bash
# from https://github.com/oneclickvirt/lxd_images
# Thanks https://images.lxd.canonical.com/
# 2025.08.17

BASE_URL="https://images.lxd.canonical.com/images"
SAVE_DIR="/home/runner/work/lxd_images/lxd_images/images_yaml"

# 创建保存目录
mkdir -p "$SAVE_DIR"

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
                PROFILE=$(echo "$PROFILES" | sort -V | tail -n1) # 选最后一个
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

# 通用函数：检查并添加包到 packages 部分
add_packages_if_not_exists() {
    local yaml_file="$1"
    local insert_after="$2"
    local packages="$3"
    
    # 检查是否已经添加过这些包
    if grep -q "curl" "$yaml_file" && grep -q "wget" "$yaml_file" && grep -q "openssh-server" "$yaml_file"; then
        echo "Packages already added to $yaml_file, skipping..."
        return 0
    fi
    
    # 添加包
    sed -i "/$insert_after/ a\\$packages" "$yaml_file"
}

# 通用函数：添加配置内容到文件末尾（如果不存在）
add_config_if_not_exists() {
    local yaml_file="$1"
    local content_file="$2"
    local lines_from_end="$3"
    
    # 检查是否已经添加过配置（通过检查特定标识）
    if grep -q "root:root" "$yaml_file" || grep -q "PermitRootLogin yes" "$yaml_file"; then
        echo "Configuration already added to $yaml_file, skipping..."
        return 0
    fi
    
    local insert_content=$(cat "$content_file")
    local line_number=$(($(wc -l <"$yaml_file") - $lines_from_end))
    head -n $line_number "$yaml_file" >temp.yaml
    echo "$insert_content" >>temp.yaml
    tail -n $lines_from_end "$yaml_file" >>temp.yaml
    mv temp.yaml "$yaml_file"
}

# 通用函数：直接添加配置到文件末尾（如果不存在）
add_config_to_end_if_not_exists() {
    local yaml_file="$1"
    local content_file="$2"
    
    # 检查是否已经添加过配置
    if grep -q "root:root" "$yaml_file" || grep -q "PermitRootLogin yes" "$yaml_file"; then
        echo "Configuration already added to $yaml_file, skipping..."
        return 0
    fi
    
    local insert_content=$(cat "$content_file")
    cat "$yaml_file" >temp.yaml
    echo "" >>temp.yaml
    echo "$insert_content" >>temp.yaml
    mv temp.yaml "$yaml_file"
}

# debian
if [ -f "debian.yaml" ]; then
    chmod 777 debian.yaml
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
    add_packages_if_not_exists "debian.yaml" "- vim" "$insert_content_1"
    add_config_if_not_exists "debian.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text" 2
    sed -i -e '/mappings:/i \ ' debian.yaml
fi

# ubuntu
if [ -f "ubuntu.yaml" ]; then
    chmod 777 ubuntu.yaml
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
    add_packages_if_not_exists "ubuntu.yaml" "- vim" "$insert_content_1"
    add_config_if_not_exists "ubuntu.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text" 2
    sed -i -e '/mappings:/i \ ' ubuntu.yaml
fi

# kali
if [ -f "kali.yaml" ]; then
    chmod 777 kali.yaml
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
    add_packages_if_not_exists "kali.yaml" "- systemd" "$insert_content_1"
    add_config_if_not_exists "kali.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text" 2
    sed -i -e '/mappings:/i \ ' kali.yaml
fi

# centos
if [ -f "centos.yaml" ]; then
    chmod 777 centos.yaml
    # epel-relase 不可用 cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "centos.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "centos.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# almalinux
if [ -f "almalinux.yaml" ]; then
    chmod 777 almalinux.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "almalinux.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "almalinux.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# rockylinux
if [ -f "rockylinux.yaml" ]; then
    chmod 777 rockylinux.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "rockylinux.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "rockylinux.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# oracle
if [ -f "oracle.yaml" ]; then
    chmod 777 oracle.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "oracle.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "oracle.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# archlinux
if [ -f "archlinux.yaml" ]; then
    chmod 777 archlinux.yaml
    # cronie 不可用 cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
    add_packages_if_not_exists "archlinux.yaml" "- which" "$insert_content_1"
    add_config_if_not_exists "archlinux.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text" 2
    sed -i -e '/mappings:/i \ ' archlinux.yaml
fi

# gentoo (注释部分保持原样)
# if [ -f "gentoo.yaml" ]; then
#     chmod 777 gentoo.yaml
#     # cronie 不可用 cron 不可用
#     insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
#     add_packages_if_not_exists "gentoo.yaml" "- sudo" "$insert_content_1"
#     add_config_if_not_exists "gentoo.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text" 3
#     sed -i -e '/environment:/i \ ' gentoo.yaml
#     sed -i 's/- default/- openrc/g' gentoo.yaml
# fi

# fedora
if [ -f "fedora.yaml" ]; then
    chmod 777 fedora.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "fedora.yaml" "- xz" "$insert_content_1"
    add_config_to_end_if_not_exists "fedora.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# alpine
if [ -f "alpine.yaml" ]; then
    chmod 777 alpine.yaml
    # cronie 不可用 cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - cronie\n    - iptables\n    - dos2unix"
    add_packages_if_not_exists "alpine.yaml" "- doas" "$insert_content_1"
    add_config_if_not_exists "alpine.yaml" "/home/runner/work/lxd_images/lxd_images/sh_insert_content.text" 2
    sed -i -e '/mappings:/i \ ' alpine.yaml
fi

# openwrt
if [ -f "openwrt.yaml" ]; then
    chmod 777 openwrt.yaml
    # cronie 不可用 cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables"
    add_packages_if_not_exists "openwrt.yaml" "- sudo" "$insert_content_1"
    add_config_to_end_if_not_exists "openwrt.yaml" "/home/runner/work/lxd_images/lxd_images/sh_insert_content.text"
fi

# opensuse
if [ -f "opensuse.yaml" ]; then
    chmod 777 opensuse.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "opensuse.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "opensuse.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

# openeuler
if [ -f "openeuler.yaml" ]; then
    chmod 777 openeuler.yaml
    # cron 不可用
    insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
    add_packages_if_not_exists "openeuler.yaml" "- vim-minimal" "$insert_content_1"
    add_config_to_end_if_not_exists "openeuler.yaml" "/home/runner/work/lxd_images/lxd_images/bash_insert_content.text"
fi

cd /home/runner/work/lxd_images/lxd_images

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
    # 如果文件不存在，则创建空文件
    if [ ! -f "$file" ]; then
        touch "$file"
    else
        # 删除重复行
        awk '!seen[$0]++' "$file" >temp && mv temp "$file"
        # 删除空行
        sed -i '/^$/d' "$file"
    fi
}

# 在开始构建之前清理旧的文件列表
rm -f x86_64_all_images.txt arm64_all_images.txt

# 不同发行版的配置
# build_or_list_images 镜像名字 镜像版本号 variants的值
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