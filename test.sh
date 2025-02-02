#!/bin/bash
# by https://github.com/oneclickvirt/lxd_images
# 2025.02.01

set -e
trap 'echo "发生错误，行号: $LINENO, 命令: $BASH_COMMAND"' ERR

if [[ $# -ne 1 ]]; then
    echo "用法: $0 <完整镜像名称>"
    exit 1
fi

image_name="$1"

if [[ "$image_name" == *"x86_64"* || "$image_name" == *"amd64"* ]]; then
    fixed_images_file="x86_64_fixed_images.txt"
elif [[ "$image_name" == *"arm64"* ]]; then
    fixed_images_file="arm64_fixed_images.txt"
else
    echo "错误：无法识别镜像架构"
    exit 1
fi

date=$(date)
{
    echo "$date"
    echo "------------------------------------------"
    echo "测试镜像: $image_name"
} >> log

test_status_file=$(mktemp)
echo "success" > "$test_status_file"

cleanup() {
    local exit_code=$?
    echo "清理资源..."
    lxc stop test 2>/dev/null || true
    lxc delete -f test 2>/dev/null || true
    lxc image delete myc 2>/dev/null || true

    if [[ -f "$test_status_file" ]]; then
        if [[ "$(cat "$test_status_file")" != "success" ]]; then
            echo "测试失败，从列表中移除镜像"
            sed -i "/$image_name/d" "$fixed_images_file"
        fi
    else
        echo "警告：test_status_file 丢失，跳过失败处理" | tee -a log
    fi

    rm -f "$test_status_file"
    rm -f lxc.tar.xz rootfs.squashfs "$image_name"
    echo "------------------------------------------" >> log

    # 检查 systemd-resolved 是否被影响，并尝试恢复
    if systemctl is-active --quiet systemd-resolved; then
        echo "重启 systemd-resolved 以恢复 DNS"
        systemctl restart systemd-resolved || true
    fi

    exit $exit_code
}

trap cleanup EXIT

echo "开始下载镜像..."
if ! curl -m 1800 -LO "https://github.com/oneclickvirt/lxd_images/releases/download/${image_name%%_*}/$image_name"; then
    echo "主下载失败，尝试备用下载源..."
    if ! curl -m 1800 -LO "https://cdn.spiritlhl.net/https://github.com/oneclickvirt/lxd_images/releases/download/${image_name%%_*}/$image_name"; then
        echo "错误：所有下载源均失败" | tee -a log
        echo "fail" > "$test_status_file"
        exit 1
    fi
fi

if [ ! -f "$image_name" ] || [ ! -s "$image_name" ]; then
    echo "错误：镜像文件不存在或为空" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi

chmod 777 "$image_name"

if ! unzip -q "$image_name"; then
    echo "错误：解压失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi

echo "$image_name" >> "$fixed_images_file"

if ! lxc image import lxd.tar.xz rootfs.squashfs --alias myc; then
    echo "错误：镜像导入失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi

if ! lxc init myc test; then
    echo "错误：容器初始化失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi

if ! lxc start test; then
    echo "错误：容器启动失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi

sleep 10

ssh_test() {
    local retries=0
    local max_retries=5
    
    while [ $retries -lt $max_retries ]; do
        if lxc exec test -- lsof -i:22 2>/dev/null | grep -q ssh; then
            echo "SSH服务正常" | tee -a log
            return 0
        fi
        echo "等待SSH服务启动，尝试 $((retries + 1))/$max_retries..." | tee -a log
        sleep $((2**retries))
        ((retries++))
    done
    
    echo "SSH服务异常" | tee -a log
    return 1
}

network_test() {
    lxc exec test -- cp /etc/resolv.conf /etc/resolv.conf.bak || true

    lxc exec test -- sh -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'

    if lxc exec test -- curl -m 10 -skL https://cdn.spiritlhl.net/https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test | grep -q "success"; then
        echo "网络连通正常" | tee -a log
        lxc exec test -- mv /etc/resolv.conf.bak /etc/resolv.conf 2>/dev/null || true
        return 0
    else
        echo "网络连接失败" | tee -a log
        lxc exec test -- mv /etc/resolv.conf.bak /etc/resolv.conf 2>/dev/null || true
        return 1
    fi
}

if ! ssh_test; then
    echo "fail" > "$test_status_file"
    exit 1
fi
if ! network_test; then
    echo "fail" > "$test_status_file"
    exit 1
fi
echo "执行重启测试..." | tee -a log
if ! lxc stop test; then
    echo "错误：容器停止失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi
if ! lxc start test; then
    echo "错误：容器重启失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi
sleep 15
if ! network_test; then
    echo "重启后网络测试失败" | tee -a log
    echo "fail" > "$test_status_file"
    exit 1
fi
echo "所有测试通过" | tee -a log
exit 0
