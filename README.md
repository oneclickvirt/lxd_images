# lxd_images


## 说明

Releases中的镜像(每日拉取镜像进行自动修补和更新)：

已预安装：wget curl openssh-server sshpass sudo cron(cronie) lsof iptables dos2unix

已预开启SSH登陆，预设SSH监听IPV4和IPV6的22端口，开启允许密码验证登陆

所有镜像均开启允许root用户进行SSH登录

默认用户名：```root```

未修改默认密码，与官方仓库一致

本仓库所有镜像的名字列表：https://github.com/oneclickvirt/lxd_images/blob/main/amd64_all_images.txt

本仓库测试无误的镜像的名字列表：https://github.com/oneclickvirt/lxd_images/blob/main/amd64_fixed_images.txt

本仓库每日检测可用性的日志：https://github.com/oneclickvirt/lxd_images/blob/main/log

本仓库的容器镜像服务于： https://github.com/oneclickvirt/incus and https://github.com/oneclickvirt/lxd

支持:

[incus的所有版本](https://github.com/lxc/incus)

LXD 版本 <= [5.18](https://github.com/canonical/lxd/releases/tag/lxd-5.18) 

incus在LXD的5.18版本分叉，不保证LXD更高版本下的容器镜像可用性

## Introduce

Mirrors in Releases (pulls mirrors daily for automatic patching and updating):

Pre-installed: wget curl openssh-server sshpass sudo cron(cronie) lsof iptables dos2unix

Pre-enabled SSH login, preset SSH listening on port 22 of IPV4 and IPV6, enabled to allow password authentication login

All mirrors are enabled to allow SSH login for root users.

Default username: ```root```.

Unchanged default password, consistent with official repository.

A list of names for all images in this repository: https://github.com/oneclickvirt/lxd_images/blob/main/amd64_all_images.txt

A list of names of images in this repository that have been tested without error: https://github.com/oneclickvirt/lxd_images/blob/main/amd64_fixed_images.txt

A log of daily availability tests for this repository: https://github.com/oneclickvirt/lxd_images/blob/main/log

This repository container images serves https://github.com/oneclickvirt/incus and https://github.com/oneclickvirt/lxd

Support:

[incus full version](https://github.com/lxc/incus)

LXD version <= [5.18](https://github.com/canonical/lxd/releases/tag/lxd-5.18)

incus forked at version 5.18 of LXD and does not guarantee container image availability under higher versions of LXD

## 测试-test

```
incus image import incus.tar.xz rootfs.squashfs --alias myc
incus init myc test
incus start test
incus exec test -- /bin/bash
```

```
incus delete -f test
incus image delete myc
```

## Sponsor

Thanks to [dartnode](https://dartnode.com/?via=server) for providing support for images compiling.

<a href="https://dartnode.com/?via=server" target="_blank">
  <img src="https://snaju.com/assets/img/logo_dark.svg" alt="ekire">
</a>

## Thanks

https://discuss.linuxcontainers.org/t/distrobuilder-how-to-compile-a-centos-container-image-in-an-ubuntu-environment-github-action/18709

https://linuxcontainers.org/incus/docs/main/

https://github.com/lxc/lxc-ci/tree/main/images

https://github.com/lxc/distrobuilder

https://go.dev/dl/
