The OpenWrt combined EFI downloader and procd agent compatibility code is
derived from lxc/distrobuilder v3.4.0, licensed under Apache-2.0. The original
license is retained in `distrobuilder-LICENSE.txt`.

Upstream sources:

- https://github.com/lxc/distrobuilder/blob/v3.4.0/sources/openwrt-http.go
- https://github.com/lxc/distrobuilder/blob/v3.4.0/generators/incus-agent.go

Changes adapt the module import path and agent names to LXD. The canonical
agent configuration-drive setup is preserved. Each compatibility fixture's
SHA256 is checked before patching an upstream builder.
