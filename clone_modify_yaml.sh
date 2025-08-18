#!/bin/bash
# from https://github.com/oneclickvirt/lxd_images
# Thanks https://images.lxd.canonical.com/
# 2025.08.18


DEFAULT_TEMPLATE_SOURCE="lxd_original"
TEMPLATE_SOURCE="$DEFAULT_TEMPLATE_SOURCE"
CURRENT_DIR=$(pwd)
SAVE_DIR="$CURRENT_DIR/images_yaml"

show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -s, --source <source>    指定模板源 (lxd_original|incus_distro|custom)"
    echo "                          lxd_original: 使用原始 LXD 镜像元数据 (默认)"
    echo "                          incus_distro: 使用 lxc-ci 官方模板"
    echo "                          custom: 使用自定义模板 URL"
    echo "  -u, --url <url>         自定义模板 URL (仅当 source=custom 时使用)"
    echo "  -h, --help              显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                    # 使用默认 LXD 原始源"
    echo "  $0 -s incus_distro                   # 使用 lxc-ci 模板"
    echo "  $0 -s custom -u https://example.com/templates"
    echo ""
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source)
            TEMPLATE_SOURCE="$2"
            shift 2
            ;;
        -u|--url)
            CUSTOM_URL="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done
if [[ ! "$TEMPLATE_SOURCE" =~ ^(lxd_original|incus_distro|custom)$ ]]; then
    echo "错误: 无效的模板源 '$TEMPLATE_SOURCE'"
    echo "支持的源: lxd_original, incus_distro, custom"
    exit 1
fi

if [[ "$TEMPLATE_SOURCE" == "custom" && -z "$CUSTOM_URL" ]]; then
    echo "错误: 使用自定义源时必须指定 URL (-u 选项)"
    exit 1
fi

echo "========================================="
echo "模板源: $TEMPLATE_SOURCE"
echo "工作目录: $CURRENT_DIR"
echo "输出目录: $SAVE_DIR"
echo "========================================="

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

setup_template_urls() {
    declare -g -A TEMPLATE_URLS
    case "$TEMPLATE_SOURCE" in
        "lxd_original")
            echo "使用原始 LXD 镜像元数据方法..."
            fetch_lxd_original_templates
            ;;
        "incus_distro")
            echo "使用 lxc-ci 官方模板..."
            TEMPLATE_BASE_URL="https://raw.githubusercontent.com/lxc/lxc-ci/refs/heads/main/images"
            TEMPLATE_URLS["debian"]="$TEMPLATE_BASE_URL/debian.yaml"
            TEMPLATE_URLS["ubuntu"]="$TEMPLATE_BASE_URL/ubuntu.yaml"
            TEMPLATE_URLS["centos"]="$TEMPLATE_BASE_URL/centos.yaml"
            TEMPLATE_URLS["almalinux"]="$TEMPLATE_BASE_URL/almalinux.yaml"
            TEMPLATE_URLS["rockylinux"]="$TEMPLATE_BASE_URL/rockylinux.yaml"
            TEMPLATE_URLS["oracle"]="$TEMPLATE_BASE_URL/oracle.yaml"
            TEMPLATE_URLS["archlinux"]="$TEMPLATE_BASE_URL/archlinux.yaml"
            TEMPLATE_URLS["fedora"]="$TEMPLATE_BASE_URL/fedora.yaml"
            TEMPLATE_URLS["alpine"]="$TEMPLATE_BASE_URL/alpine.yaml"
            TEMPLATE_URLS["openwrt"]="$TEMPLATE_BASE_URL/openwrt.yaml"
            TEMPLATE_URLS["opensuse"]="$TEMPLATE_BASE_URL/opensuse.yaml"
            TEMPLATE_URLS["kali"]="$TEMPLATE_BASE_URL/kali.yaml"
            TEMPLATE_URLS["gentoo"]="$TEMPLATE_BASE_URL/gentoo.yaml"
            ;;
        "custom")
            echo "使用自定义模板 URL: $CUSTOM_URL"
            TEMPLATE_URLS["debian"]="$CUSTOM_URL/debian.yaml"
            TEMPLATE_URLS["ubuntu"]="$CUSTOM_URL/ubuntu.yaml"
            TEMPLATE_URLS["centos"]="$CUSTOM_URL/centos.yaml"
            TEMPLATE_URLS["almalinux"]="$CUSTOM_URL/almalinux.yaml"
            TEMPLATE_URLS["rockylinux"]="$CUSTOM_URL/rockylinux.yaml"
            TEMPLATE_URLS["oracle"]="$CUSTOM_URL/oracle.yaml"
            TEMPLATE_URLS["archlinux"]="$CUSTOM_URL/archlinux.yaml"
            TEMPLATE_URLS["fedora"]="$CUSTOM_URL/fedora.yaml"
            TEMPLATE_URLS["alpine"]="$CUSTOM_URL/alpine.yaml"
            TEMPLATE_URLS["openwrt"]="$CUSTOM_URL/openwrt.yaml"
            TEMPLATE_URLS["opensuse"]="$CUSTOM_URL/opensuse.yaml"
            TEMPLATE_URLS["kali"]="$CUSTOM_URL/kali.yaml"
            TEMPLATE_URLS["gentoo"]="$CUSTOM_URL/gentoo.yaml"
            ;;
    esac
}

fetch_lxd_original_templates() {
    echo "从 images.lxd.canonical.com 获取镜像列表..."
    IMAGES_JSON=$(curl -s "https://images.lxd.canonical.com/streams/v1/images.json")
    if [ -z "$IMAGES_JSON" ]; then
        echo "错误: 无法获取镜像列表"
        exit 1
    fi
    declare -g -A LATEST_YAML
    SYSTEMS="debian ubuntu kali centos almalinux rockylinux oracle archlinux fedora alpine openwrt opensuse openeuler gentoo"
    BASE_URL="https://images.lxd.canonical.com/images"
    for SYSTEM in $SYSTEMS; do
        echo "处理系统: $SYSTEM"
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
            TEMPLATE_URLS[$SYSTEM]="$YAML_URL"
            echo "找到: $SYSTEM -> $YAML_URL"
        else
            echo "警告: 未找到 $SYSTEM 的合适镜像"
        fi
    done
}

download_and_modify_templates() {
    declare -A FILES_TO_MODIFY
    echo "检查更新..."
    cd "$SAVE_DIR"
    for SYS in "${!TEMPLATE_URLS[@]}"; do
        YAML_FILE="$SYS.yaml"
        YAML_URL="${TEMPLATE_URLS[$SYS]}"
        if [ -n "$YAML_URL" ]; then
            needs_update=$(check_remote_file_updated "$YAML_URL" "$YAML_FILE")
            if [ "$needs_update" = "true" ]; then
                echo "[$SYS] 远程文件已更新，将重新下载和修改"
                FILES_TO_MODIFY[$SYS]="$YAML_URL"
                rm -f "${YAML_FILE}.modified"
            else
                echo "[$SYS] 文件是最新的，跳过"
            fi
        fi
    done
    echo "下载 YAML 文件..."
    for SYS in "${!TEMPLATE_URLS[@]}"; do
        YAML_FILE="$SYS.yaml"
        YAML_URL="${TEMPLATE_URLS[$SYS]}"
        
        if [[ -v FILES_TO_MODIFY[$SYS] ]] && [ -n "$YAML_URL" ]; then
            echo "从以下地址下载: $YAML_URL"
            if curl -s -o "$YAML_FILE" "$YAML_URL"; then
                if [ -s "$YAML_FILE" ]; then
                    echo "已下载: $YAML_FILE"
                    save_remote_metadata "$YAML_URL" "$YAML_FILE"
                else
                    echo "下载的文件为空，删除: $YAML_FILE"
                    rm -f "$YAML_FILE" "${YAML_FILE}.meta"
                fi
            else
                echo "下载失败: $YAML_URL"
            fi
        else
            echo "跳过（已存在且最新）: $YAML_FILE"
        fi
    done
}

modify_yaml_file() {
    local file_name="$1"
    local insert_point="$2"
    local packages="$3"
    local use_bash_insert="$4"
    if [ -f "${file_name}.modified" ]; then
        echo "跳过 ${file_name} - 已修改"
        return
    fi
    if [ ! -f "$file_name" ]; then
        echo "警告: $file_name 未找到"
        return
    fi
    echo "修改: $file_name"
    chmod 777 "$file_name"
    if grep -q "$insert_point" "$file_name"; then
        sed -i "/${insert_point}/ a\\${packages}" "$file_name"
    else
        echo "警告: 在 $file_name 中未找到插入点 '$insert_point'"
        echo "packages:" >> "$file_name"
        echo -e "$packages" >> "$file_name"
    fi
    if [ "$use_bash_insert" = "true" ]; then
        insert_content_2=$(cat "$CURRENT_DIR/bash_insert_content.text" 2>/dev/null || echo "# bash_insert_content.text not found")
    else
        insert_content_2=$(cat "$CURRENT_DIR/sh_insert_content.text" 2>/dev/null || echo "# sh_insert_content.text not found")
    fi
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
    touch "${file_name}.modified"
    echo "已修改: $file_name"
}

perform_yaml_modifications() {
    echo "开始修改 YAML 文件..."
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
}

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
                    echo "文件未找到: $url"
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

generate_image_lists() {
    cd "$CURRENT_DIR"
    echo "生成镜像列表..."
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
}

main() {
    setup_template_urls
    download_and_modify_templates
    perform_yaml_modifications
    generate_image_lists
    echo "模板文件位置: $SAVE_DIR"
}

check_dependencies() {
    local missing_deps=()
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    if ! command -v jq &> /dev/null; then
        missing_deps+=("jq")
    fi
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo "错误: 缺少以下依赖:"
        printf ' - %s\n' "${missing_deps[@]}"
        echo ""
        echo "请安装缺少的依赖后重试"
        exit 1
    fi
}
check_dependencies
main
