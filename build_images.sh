#!/bin/bash
# 从 https://github.com/oneclickvirt/lxd_images 获取

run_funct="${1:-debian}"
is_build_image="${2:-false}"
build_arch="${3:-amd64}"
zip_name_list=()
opath=$(pwd)
rm -rf *.tar.xz
ls

# 检查并安装依赖工具
if command -v apt-get >/dev/null 2>&1; then
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
    for ((i = 0; i < len; i++)); do
        version=${versions[i]}
        ver_num=${ver_nums[i]}
        for arch in "${architectures[@]}"; do
            for variant in "${variants[@]}"; do
                if [ "$is_build_image" == true ]; then
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
                            EXTRA_ARGS="-o source.same_as=3.19"
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
                            ${EXTRA_ARGS} )
                        case "$run_funct" in
                            gentoo)
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
                            if [ -f lxd.tar.xz ] && [ -f rootfs.squashfs ]; then
                                total_size=$(($(stat -c%s lxd.tar.xz) + $(stat -c%s rootfs.squashfs)))
                                if [ "$total_size" -gt $((10 * 1024 * 1024)) ]; then
                                    echo "Build artifacts detected (lxd.tar.xz + rootfs.squashfs), total size > 10MB, assuming success"
                                    success=true
                                    break
                                else
                                    echo "Artifacts found but total size <= 10MB, ignoring..."
                                fi
                            fi
                        done
                        if ! $success; then
                            echo "All build attempts failed, skipping this distro."
                            continue
                        fi
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
                        zip "${zip_file}" lxd.tar.xz rootfs.squashfs
                        rm -f lxd.tar.xz rootfs.squashfs
                        if [[ -f "$zip_file" ]]; then
                            file_size_bytes=$(stat -c%s "$zip_file")
                            file_size_mb=$(awk "BEGIN {printf \"%.2f\", $file_size_bytes/1024/1024}")
                            echo "zipfile: $zip_file size: ${file_size_mb} MB"
                        fi
                    else
                        echo "Expected artifacts not found, nothing to zip."
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
    build_or_list_images "7 8 9-stream" "7 8 9-stream" "openrc systemd"
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
    echo "Invalid distribution specified."
    ;;
esac
