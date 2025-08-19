# lxd_images

![Downloads](https://ghdownload.spiritlhl.net/oneclickvirt/lxd_images)

[![Clone Yaml](https://github.com/oneclickvirt/lxd_images/actions/workflows/clone_yaml.yml/badge.svg)](https://github.com/oneclickvirt/lxd_images/actions/workflows/clone_yaml.yml)

[![Multi-Distro Images Build](https://github.com/oneclickvirt/lxd_images/actions/workflows/build.yml/badge.svg)](https://github.com/oneclickvirt/lxd_images/actions/workflows/build.yml)

[![Multi-Distro KVM Images Builder](https://github.com/oneclickvirt/lxd_images/actions/workflows/build_vm.yml/badge.svg)](https://github.com/oneclickvirt/lxd_images/actions/workflows/build_vm.yml)

## 说明

Releases中的镜像(每日拉取镜像进行自动修补和更新)：

已预安装：wget curl openssh-server sshpass sudo cron(cronie) lsof iptables dos2unix

已预开启SSH登陆，预设SSH监听IPV4和IPV6的22端口，开启允许密码验证登陆

所有镜像均开启允许root用户进行SSH登录

默认用户名：```root```

未修改默认密码，与官方仓库一致

本仓库所有镜像的名字列表：[x86_64_all_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/x86_64_all_images.txt) 和 [arm64_all_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/arm64_all_images.txt)

本仓库测试无误的镜像的名字列表：[x86_64_fixed_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/x86_64_fixed_images.txt) 和 [arm64_fixed_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/arm64_fixed_images.txt)

本仓库的容器镜像服务于： https://github.com/oneclickvirt/lxd

远程镜像源地址: https://lxdimages.spiritlhl.net/

## Introduce

Mirrors in Releases (pulls mirrors daily for automatic patching and updating):

Pre-installed: wget curl openssh-server sshpass sudo cron(cronie) lsof iptables dos2unix

Pre-enabled SSH login, preset SSH listening on port 22 of IPV4 and IPV6, enabled to allow password authentication login

All mirrors are enabled to allow SSH login for root users.

Default username: ```root```.

Unchanged default password, consistent with official repository.

A list of names for all images in this repository: [x86_64_all_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/x86_64_all_images.txt) and [arm64_all_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/arm64_all_images.txt)

A list of names of images in this repository that have been tested without error: [x86_64_fixed_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/x86_64_fixed_images.txt) and [arm64_fixed_images.txt](https://github.com/oneclickvirt/lxd_images/blob/main/arm64_fixed_images.txt)

This repository container images serves https://github.com/oneclickvirt/lxd

Remote images source address: https://lxdimages.spiritlhl.net/

## 测试-test

```
lxc image import lxd.tar.xz rootfs.squashfs --alias myc
lxc init myc test
lxc start test
lxc exec test -- /bin/bash
```

```
lxc delete -f test
lxc image delete myc
```

## Sponsor

[![Powered by DartNode](https://dartnode.com/branding/DN-Open-Source-sm.png)](https://dartnode.com?aff=bonus "Powered by DartNode - Free VPS for Open Source")

## Thanks

https://images.lxd.canonical.com/

https://github.com/canonical/lxd-imagebuilder

https://go.dev/dl/
