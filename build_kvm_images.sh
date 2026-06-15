#!/bin/bash
# 从 https://github.com/oneclickvirt/lxd_images 获取

run_funct="${1:-debian}"
is_build_image="${2:-false}"
build_arch="${3:-amd64}"
zip_name_list=()
opath=$(pwd)
rm -rf *.tar.xz *.qcow2
if [ "$is_build_image" == true ]; then
    ls
fi

if [[ "$run_funct" == "kali" || "$run_funct" == "oracle" ]]; then
    echo "${run_funct}.yaml lacks complete VM boot support." >&2
    exit 0
fi

# 检查并安装依赖工具
if [ "$is_build_image" == true ] && command -v apt-get >/dev/null 2>&1; then
    if ! command -v sudo >/dev/null 2>&1; then
        apt-get install sudo -y
    fi
    if ! command -v zip >/dev/null 2>&1; then
        sudo apt-get install zip -y
    fi
    if ! command -v jq >/dev/null 2>&1; then
        sudo apt-get install jq -y
    fi
    if ! command -v snap >/dev/null 2>&1; then
        sudo apt-get install snapd -y
    fi
    if ! command -v umoci >/dev/null 2>&1; then
        sudo apt-get install umoci -y
    fi
    sudo systemctl start snapd
    sleep 10
    if ! command -v lxd-imagebuilder >/dev/null 2>&1; then
        sudo snap install --edge lxd-imagebuilder --classic
    fi
    if ! command -v debootstrap >/dev/null 2>&1; then
        sudo apt-get install debootstrap -y
    fi
    sudo apt-get install -y btrfs-progs dosfstools qemu-kvm
fi

# 架构检查和转换
if [ "${build_arch}" == "x86_64" ] || [ "${build_arch}" == "amd64" ]; then
    build_arch="amd64"
elif [ "${build_arch}" == "aarch64" ] || [ "${build_arch}" == "arm64" ]; then
    build_arch="arm64"
else
    echo "不支持的架构: ${build_arch}"
    exit 1
fi

get_versions() {
    local system=$1
    local yaml_file="./images_yaml/$system.yaml"
    if [ -f "$yaml_file" ]; then
        versions=$(awk '
            /^[[:space:]]*releases:/ {
                getline
                while ($0 ~ /^[[:space:]]*-[[:space:]]*/) {
                    gsub(/^[[:space:]]*-[[:space:]]*/, "")
                    gsub(/"/, "")
                    if ($0 != "" && !seen[$0]) {
                        releases[++count] = $0
                        seen[$0] = 1
                    }
                    getline
                }
            }
            END {
                for (i = 1; i <= count; i++) {
                    if (i > 1) printf " "
                    printf "%s", releases[i]
                }
            }
        ' "$yaml_file")
        echo "${versions,,}"
    else
        echo ""
    fi
}

requires_secureboot_disabled() {
    case "$run_funct" in
        alpine|archlinux|centos|fedora|gentoo|opensuse|openeuler|openwrt|rockylinux)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

patch_lxd_metadata_for_kvm() {
    local zip_file="$1"
    local image_name="${zip_file%.zip}"
    local temp_dir
    temp_dir=$(mktemp -d) || return 1

    # Extract LXD metadata tarball
    if ! tar -xf lxd.tar.xz -C "$temp_dir" 2>/dev/null; then
        rm -rf "$temp_dir"
        echo "Failed to extract lxd.tar.xz for ${image_name}" >&2
        return 1
    fi

    # Ensure secureboot is disabled if the distro requires it
    if requires_secureboot_disabled; then
        if [ -f "$temp_dir/metadata.yaml" ]; then
            if ! grep -q 'requirements.secureboot:' "$temp_dir/metadata.yaml" 2>/dev/null; then
                echo "requirements:" >> "$temp_dir/metadata.yaml"
                echo "  secureboot: false" >> "$temp_dir/metadata.yaml"
            elif ! grep -q 'requirements.secureboot:[[:space:]]*"false"\|requirements.secureboot:[[:space:]]*false' "$temp_dir/metadata.yaml" 2>/dev/null; then
                sed -i 's/requirements.secureboot:.*/requirements.secureboot: false/' "$temp_dir/metadata.yaml"
            fi
        fi
    fi

    # Repack the tarball
    if [ -f "$temp_dir/rootfs.squashfs" ] || [ -d "$temp_dir/rootfs" ]; then
        if ! tar -C "$temp_dir" -cJf new_lxd.tar.xz metadata.yaml templates/ 2>/dev/null; then
            # Fallback: just metadata.yaml
            if ! tar -C "$temp_dir" -cJf new_lxd.tar.xz metadata.yaml 2>/dev/null; then
                rm -rf "$temp_dir"
                echo "Failed to repack lxd.tar.xz for ${image_name}" >&2
                return 1
            fi
        fi
        # Replace original
        mv new_lxd.tar.xz lxd.tar.xz
    elif ! tar -C "$temp_dir" -cJf new_lxd.tar.xz metadata.yaml 2>/dev/null; then
        rm -rf "$temp_dir"
        echo "Failed to repack lxd.tar.xz for ${image_name}" >&2
        return 1
    else
        mv new_lxd.tar.xz lxd.tar.xz
    fi

    rm -rf "$temp_dir"
    return 0
}

validate_vm_artifacts() {
    local zip_file="$1"
    local image_name="${zip_file%.zip}"

    # Verify lxd.tar.xz exists and contains metadata.yaml
    if [ ! -f lxd.tar.xz ]; then
        echo "lxd.tar.xz for ${image_name} is missing" >&2
        return 1
    fi

    if ! tar -tf lxd.tar.xz metadata.yaml >/dev/null 2>&1; then
        echo "lxd.tar.xz for ${image_name} does not contain metadata.yaml" >&2
        return 1
    fi

    if ! tar -xOf lxd.tar.xz metadata.yaml 2>/dev/null | grep -q '^architecture:'; then
        echo "metadata.yaml for ${image_name} is missing architecture" >&2
        return 1
    fi

    if requires_secureboot_disabled; then
        if ! tar -xOf lxd.tar.xz metadata.yaml 2>/dev/null | grep -q '^[[:space:]]*requirements\.secureboot:[[:space:]]*["'"'"']*false["'"'"']*[[:space:]]*$'; then
            echo "metadata.yaml for ${image_name} must declare requirements.secureboot=false" >&2
            return 1
        fi
    fi

    # Verify disk.qcow2
    if [ ! -f disk.qcow2 ]; then
        echo "disk.qcow2 for ${image_name} is missing" >&2
        return 1
    fi

    if command -v qemu-img >/dev/null 2>&1; then
        if ! qemu-img info disk.qcow2 >/dev/null 2>&1; then
            echo "qemu-img cannot read disk.qcow2 for ${image_name}" >&2
            return 1
        fi

        if command -v jq >/dev/null 2>&1; then
            local disk_info
            disk_info=$(qemu-img info --output=json disk.qcow2 2>/dev/null || true)
            local disk_format
            disk_format=$(printf '%s' "$disk_info" | jq -r '.format // empty' 2>/dev/null || true)
            local virtual_size
            virtual_size=$(printf '%s' "$disk_info" | jq -r '."virtual-size" // 0' 2>/dev/null || true)

            if [ "$disk_format" != "qcow2" ] && [ -n "$disk_format" ]; then
                echo "disk.qcow2 for ${image_name} has unexpected format: ${disk_format}" >&2
                return 1
            fi

            if [ "$virtual_size" -le 0 ] 2>/dev/null && [ -n "$virtual_size" ]; then
                echo "disk.qcow2 for ${image_name} has invalid virtual size" >&2
                return 1
            fi
        fi
    fi

    return 0
}

build_or_list_kvm_images() {
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
                if [[ "$run_funct" == "centos" || "$run_funct" == "fedora" || "$run_funct" == "openeuler" ]]; then
                    manager="yum"
                elif [[ "$run_funct" == "kali" || "$run_funct" == "ubuntu" || "$run_funct" == "debian" ]]; then
                    manager="apt"
                elif [[ "$run_funct" == "almalinux" || "$run_funct" == "rockylinux" || "$run_funct" == "oracle" ]]; then
                    manager="dnf"
                elif [[ "$run_funct" == "archlinux" ]]; then
                    manager="pacman"
                elif [[ "$run_funct" == "alpine" ]]; then
                    manager="apk"
                elif [[ "$run_funct" == "openwrt" ]]; then
                    manager="opkg"
                    [ "${version}" = "snapshot" ] && manager="apk"
                elif [[ "$run_funct" == "gentoo" ]]; then
                    manager="portage"
                elif [[ "$run_funct" == "opensuse" ]]; then
                    manager="zypper"
                else
                    echo "Unsupported distribution: $run_funct"
                    exit 1
                fi
                
                EXTRA_ARGS=""
                
                # 架构转换和特殊参数设置
                case "$run_funct" in
                    "centos")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [ "$version" = "7" ] && [ "${arch}" != "amd64" ] && [ "${arch}" != "x86_64" ]; then
                            EXTRA_ARGS="-o source.url=http://mirror.math.princeton.edu/pub/centos-altarch/ -o source.skip_verification=true"
                        fi
                        if [ "$version" = "8-Stream" ] || [ "$version" = "9-Stream" ]; then
                            EXTRA_ARGS="${EXTRA_ARGS} -o source.variant=boot"
                        fi
                        if [ "$version" = "9-Stream" ]; then
                            EXTRA_ARGS="${EXTRA_ARGS} -o source.url=https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream"
                        fi
                        ;;
                    "rockylinux"|"almalinux")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        EXTRA_ARGS="-o source.variant=boot"
                        ;;
                    "oracle")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [[ "$version" == "9" ]]; then
                            EXTRA_ARGS="-o source.url=https://yum.oracle.com/ISOS/OracleLinux"
                        fi
                        ;;
                    "archlinux")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [ "${arch}" != "amd64" ] && [ "${arch}" != "i386" ] && [ "${arch}" != "x86_64" ]; then
                            EXTRA_ARGS="-o source.url=http://os.archlinuxarm.org"
                        fi
                        ;;
                    "alpine")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [ "${version}" = "edge" ]; then
                            EXTRA_ARGS="-o source.same_as=3.21"
                        fi
                        ;;
                    "fedora"|"openeuler"|"opensuse")
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        ;;
                    "debian"|"kali")
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                        ;;
                    "ubuntu")
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                        if [ "${arch}" != "amd64" ] && [ "${arch}" != "i386" ] && [ "${arch}" != "x86_64" ]; then
                            EXTRA_ARGS="-o source.url=http://ports.ubuntu.com/ubuntu-ports"
                        fi
                        ;;
                    "gentoo")
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                        if [ "${variant}" = "cloud" ]; then
                            EXTRA_ARGS="-o source.variant=openrc"
                        else
                            EXTRA_ARGS="-o source.variant=${variant}"
                        fi
                        ;;
                esac
                
                if [ "$is_build_image" == true ]; then
                    if command -v lxd-imagebuilder >/dev/null 2>&1; then
                        BUILDER_CMD=( sudo lxd-imagebuilder build-lxd "${opath}/images_yaml/${run_funct}.yaml" --vm \
                            -o image.architecture="${arch}" \
                            -o image.variant="${variant}" \
                            -o packages.manager="${manager}" \
                            ${EXTRA_ARGS} )
                        
                        case "$run_funct" in
                            gentoo|archlinux)
                                RELEASE_OPTS=( "" )
                                ;;
                            kali|ubuntu|debian|alpine)
                                RELEASE_OPTS=( "" "-o image.release=${version}" )
                                ;;
                            *)
                                RELEASE_OPTS=( "" "-o image.release=${ver_num}" "-o image.release=${version}" )
                                ;;
                        esac
                        
                        success=false
                        for rel in "${RELEASE_OPTS[@]}"; do
                            echo "Running: ${BUILDER_CMD[*]} $rel"
                            if "${BUILDER_CMD[@]}" $rel; then
                                echo "Command succeeded"
                                success=true
                                break
                            fi
                            # 检查是否有构建产物
                            if [ -f lxd.tar.xz ] && [ -f disk.qcow2 ]; then
                                total_size=$(($(stat -c%s lxd.tar.xz) + $(stat -c%s disk.qcow2)))
                                if [ "$total_size" -gt $((10 * 1024 * 1024)) ]; then
                                    echo "Build artifacts detected (lxd.tar.xz + disk.qcow2), total size > 10MB, assuming success"
                                    success=true
                                    break
                                else
                                    echo "Artifacts found but total size <= 10MB, ignoring..."
                                fi
                            fi
                        done
                        
                        if ! $success; then
                            echo "Build failed for ${run_funct} ${version} ${arch} ${variant}; removing partial VM artifacts"
                            rm -f lxd.tar.xz disk.qcow2 disk_compressed.qcow2
                            continue
                        fi
                    else
                        echo "lxd-imagebuilder not found"
                        continue
                    fi
                    
                    du -sh *
                    
                    # 架构标签转换用于文件命名
                    case "$arch" in
                      x86_64)
                        arch_label="amd64"
                        ;;
                      aarch64)
                        arch_label="arm64"
                        ;;
                      *)
                        arch_label="$arch"
                        ;;
                    esac
                    
                    zip_file="${run_funct}_${ver_num}_${version}_${arch_label}_${variant}_kvm.zip"
                    
                    if [ -f lxd.tar.xz ] && [ -f disk.qcow2 ]; then
                        if ! patch_lxd_metadata_for_kvm "$zip_file"; then
                            echo "Failed to patch metadata for ${zip_file}; skipping package"
                            rm -f lxd.tar.xz disk.qcow2 disk_compressed.qcow2
                            continue
                        fi

                        if command -v qemu-img >/dev/null 2>&1; then
                            qemu-img convert -O qcow2 -c disk.qcow2 disk_compressed.qcow2 && mv disk_compressed.qcow2 disk.qcow2 || true
                        fi

                        if validate_vm_artifacts "$zip_file"; then
                            zip -9 "${zip_file}" lxd.tar.xz disk.qcow2
                        else
                            echo "VM artifacts failed validation for ${zip_file}; skipping package"
                        fi
                    else
                        echo "Expected artifacts (lxd.tar.xz and disk.qcow2) not found, nothing to zip."
                    fi

                    rm -f lxd.tar.xz disk.qcow2 disk_compressed.qcow2

                    if [[ -f "$zip_file" ]]; then
                        file_size_bytes=$(stat -c%s "$zip_file")
                        file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size_bytes/1024/1024}")
                        echo "zipfile: $zip_file size: ${file_size_mb} MB"
                    fi
                else
                    # 架构标签转换用于列表输出
                    case "$arch" in
                      x86_64)
                        arch_label="amd64"
                        ;;
                      aarch64)
                        arch_label="arm64"
                        ;;
                      *)
                        arch_label="$arch"
                        ;;
                    esac
                    zip_name_list+=("${run_funct}_${ver_num}_${version}_${arch_label}_${variant}_kvm.zip")
                fi
            done
        done
    done
    
    if [ "$is_build_image" == false ]; then
        echo "${zip_name_list[@]}"
    fi
}

# 主要的发行版配置
case "$run_funct" in
debian)
    build_or_list_kvm_images "buster bullseye bookworm trixie" "10 11 12 13" "cloud default"
    ;;
ubuntu)
    build_or_list_kvm_images "bionic focal jammy lunar mantic noble" "18.04 20.04 22.04 23.04 23.10 24.04" "cloud default"
    ;;
kali)
    build_or_list_kvm_images "kali-rolling" "latest" "cloud default"
    ;;
archlinux)
    build_or_list_kvm_images "current" "current" "cloud default"
    ;;
gentoo)
    build_or_list_kvm_images "current" "current" "openrc systemd"
    ;;
centos)
    build_or_list_kvm_images "7 8-Stream 9-Stream" "7 8 9" "cloud default"
    ;;
oracle)
    build_or_list_kvm_images "7 8 9" "7 8 9" "cloud default"
    ;;
openeuler)
    build_or_list_kvm_images "24.03" "24.03" "cloud default"
    ;;
openwrt)
    build_or_list_kvm_images "23.05 24.10 snapshot" "23.05 24.10 snapshot" "cloud default"
    ;;
almalinux | rockylinux | alpine | fedora | opensuse)
    versions=$(get_versions "$run_funct")
    releases=$(get_versions "$run_funct")
    if [[ -z "$versions" && -n "$releases" ]]; then
        versions="$releases"
    elif [[ -z "$releases" && -n "$versions" ]]; then
        releases="$versions"
    fi
    build_or_list_kvm_images "$versions" "$releases" "cloud default"
    ;;
*)
    echo "Invalid distribution specified."
    ;;
esac