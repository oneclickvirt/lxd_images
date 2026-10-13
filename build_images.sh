#!/bin/bash
set -eo pipefail
# 从 https://github.com/oneclickvirt/lxd_images 获取

run_funct="${1:-debian}"
is_build_image="${2:-false}"
build_arch="${3:-amd64}"
zip_name_list=()
opath=$(pwd)
selected_images=0
[[ "$is_build_image" == true || "$is_build_image" == false ]] || { echo "Invalid build mode" >&2; exit 1; }
[[ "$build_arch" =~ ^(amd64|x86_64|arm64|aarch64)$ ]] || { echo "Invalid image architecture" >&2; exit 1; }
[[ "${CI_IMAGE_RELEASES:-}" =~ ^[A-Za-z0-9._\ -]*$ ]] || { echo "Invalid release selector" >&2; exit 1; }
if [[ "$is_build_image" == true ]]; then rm -f -- incus.tar.xz lxd.tar.xz rootfs.squashfs rootfs.tar.xz; fi
if [[ "$is_build_image" == true ]]; then ls; fi

# 检查并安装依赖工具
if [ "$is_build_image" == true ] && command -v apt-get >/dev/null 2>&1; then
    # ubuntu debian kali
    if ! command -v sudo >/dev/null 2>&1; then
        apt-get install sudo -y
    fi
    if ! command -v zip >/dev/null 2>&1; then
        sudo apt-get install zip -y
    fi
    if ! command -v jq >/dev/null 2>&1; then
        sudo apt-get install jq -y
    fi
    if ! command -v umoci >/dev/null 2>&1; then
        sudo apt-get install umoci -y
    fi
    if ! command -v snap >/dev/null 2>&1; then
        sudo apt-get install snapd -y
    fi
    sudo systemctl start snapd
    sleep 10
    if ! command -v lxd-imagebuilder >/dev/null 2>&1; then
        sudo snap install --edge lxd-imagebuilder --classic
        lxd-imagebuilder --version
    fi
    if ! command -v debootstrap >/dev/null 2>&1; then
        sudo apt-get install debootstrap -y
    fi
fi

# 架构检查
if [ "${build_arch}" == "x86_64" ] || [ "${build_arch}" == "amd64" ]; then
    # build_arch="x86_64"
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

# 构建或列出镜像
build_or_list_images() {
    local versions=()
    local ver_nums=()
    local variants=()
    read -ra versions <<<"$1"
    read -ra ver_nums <<<"$2"
    read -ra variants <<<"$3"
    local architectures=("$build_arch")
    local len=${#versions[@]}
    if (( len == 0 )); then echo "No image releases were obtained from the configured source" >&2; return 1; fi
    for ((i = 0; i < len; i++)); do
        version=${versions[i]}
        ver_num=${ver_nums[i]}
        if [[ -n "${CI_IMAGE_RELEASES:-}" && " ${CI_IMAGE_RELEASES} " != *" ${version} "* && " ${CI_IMAGE_RELEASES} " != *" ${ver_num} "* ]]; then
            continue
        fi
        for arch in "${architectures[@]}"; do
            for variant in "${variants[@]}"; do
                selected_images=$((selected_images + 1))
                if [ "$is_build_image" == true ]; then
                    rm -f -- incus.tar.xz lxd.tar.xz rootfs.squashfs rootfs.tar.xz disk.qcow2 disk_compressed.qcow2
                    if [[ "$run_funct" == "kali" || "$run_funct" == "ubuntu" || "$run_funct" == "debian" ]]; then
                        manager="apt"
                    elif [[ "$run_funct" == "centos" || "$run_funct" == "fedora" || "$run_funct" == "openeuler" ]]; then
                        manager="yum"
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
                    fi
                    EXTRA_ARGS=""
                    if [[ "$run_funct" == "alpine" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [ "${version}" = "edge" ]; then
                            EXTRA_ARGS="-o source.same_as=3.21"
                        fi
                    elif [[ "$run_funct" == "centos" ]]; then
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
                    elif [[ "$run_funct" == "rockylinux" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        EXTRA_ARGS="-o source.variant=boot"
                    elif [[ "$run_funct" == "almalinux" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        EXTRA_ARGS="-o source.variant=boot"
                    elif [[ "$run_funct" == "oracle" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [[ "$version" == "9" ]]; then
                            EXTRA_ARGS="-o source.url=https://yum.oracle.com/ISOS/OracleLinux"
                        fi
                    elif [[ "$run_funct" == "archlinux" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                        if [ "${arch}" != "amd64" ] && [ "${arch}" != "i386" ] && [ "${arch}" != "x86_64" ]; then
                            EXTRA_ARGS="-o source.url=http://os.archlinuxarm.org"
                        fi
                    elif [[ "$run_funct" == "fedora" || "$run_funct" == "openeuler" || "$run_funct" == "opensuse" ]]; then
                        [ "${arch}" = "amd64" ] && arch="x86_64"
                        [ "${arch}" = "arm64" ] && arch="aarch64"
                    elif [[ "$run_funct" == "gentoo" ]]; then
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                        if [ "${variant}" = "cloud" ]; then
                            EXTRA_ARGS="-o source.variant=openrc"
                        else
                            EXTRA_ARGS="-o source.variant=${variant}"
                        fi
                    elif [[ "$run_funct" == "debian" ]]; then
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                    elif [[ "$run_funct" == "ubuntu" ]]; then
                        [ "${arch}" = "x86_64" ] && arch="amd64"
                        [ "${arch}" = "aarch64" ] && arch="arm64"
                        if [ "${arch}" != "amd64" ] && [ "${arch}" != "i386" ] && [ "${arch}" != "x86_64" ]; then
                            EXTRA_ARGS="-o source.url=http://ports.ubuntu.com/ubuntu-ports"
                        fi
                    fi
                    if command -v lxd-imagebuilder >/dev/null 2>&1; then
                        BUILDER_CMD=( sudo lxd-imagebuilder build-lxd "${opath}/images_yaml/${run_funct}.yaml" \
                            -o image.architecture="${arch}" \
                            -o image.variant="${variant}" \
                            -o packages.manager="${manager}" \
                            ${EXTRA_ARGS} )
                        if [[ "$run_funct" != gentoo && "$run_funct" != archlinux ]]; then
                            BUILDER_CMD+=( -o "image.release=${version}" )
                        fi
                        echo "Running: ${BUILDER_CMD[*]}"
                        if ! "${BUILDER_CMD[@]}"; then
                            echo "Image builder failed; preserving the previous release" >&2
                            rm -f lxd.tar.xz rootfs.squashfs disk.qcow2 disk_compressed.qcow2
                            return 1
                        fi
                    else
                        echo "lxd-imagebuilder not found" >&2
                        return 1
                    fi
                    du -sh *
                    if [ -f lxd.tar.xz ] && [ -f rootfs.squashfs ]; then
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
                        zip_file="${run_funct}_${ver_num}_${version}_${arch_label}_${variant}.zip"
                        rm -f -- "$zip_file"
                        zip -9 "${zip_file}" lxd.tar.xz rootfs.squashfs
                        rm -f lxd.tar.xz rootfs.squashfs
                        if [[ -f "$zip_file" ]]; then
                            file_size_bytes=$(stat -c%s "$zip_file")
                            file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size_bytes/1024/1024}")
                            echo "zipfile: $zip_file size: ${file_size_mb} MB"
                        fi
                    else
                        echo "Expected artifacts not found" >&2
                        return 1
                    fi
                else
                    zip_name_list+=("${run_funct}_${ver_num}_${version}_${arch}_${variant}.zip")
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
    build_or_list_images "buster bullseye bookworm trixie" "10 11 12 13" "cloud default"
    ;;
ubuntu)
    build_or_list_images "bionic focal jammy lunar mantic noble" "18.04 20.04 22.04 23.04 23.10 24.04" "cloud default"
    ;;
kali)
    build_or_list_images "kali-rolling" "latest" "cloud default"
    ;;
archlinux)
    build_or_list_images "current" "current" "cloud default"
    ;;
gentoo)
    build_or_list_images "current" "current" "openrc systemd"
    ;;
centos)
    build_or_list_images "7 8-Stream 9-Stream" "7 8 9" "cloud default"
    ;;
oracle)
    build_or_list_images "7 8 9" "7 8 9" "cloud default"
    ;;
openeuler)
    build_or_list_images "24.03" "24.03" "cloud default"
    ;;
openwrt)
    build_or_list_images "23.05 24.10 snapshot" "23.05 24.10 snapshot" "cloud default"
    ;;
almalinux | rockylinux | alpine | fedora | opensuse)
    versions=$(get_versions "$run_funct")
    releases=$(get_versions "$run_funct")
    if [[ -z "$versions" && -n "$releases" ]]; then
        versions="$releases"
    elif [[ -z "$releases" && -n "$versions" ]]; then
        releases="$versions"
    fi
    build_or_list_images "$versions" "$releases" "cloud default"
    ;;
*)
    echo "Invalid distribution specified." >&2
    exit 1
    ;;
esac

(( selected_images > 0 )) || { echo "No images match the requested release" >&2; exit 1; }
