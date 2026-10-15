The OpenWrt combined EFI downloader and procd agent compatibility code is
derived from lxc/distrobuilder v3.4.0, licensed under Apache-2.0. The original
license is retained in `distrobuilder-LICENSE.txt`.

Upstream sources:

- https://github.com/lxc/distrobuilder/blob/v3.4.0/sources/openwrt-http.go
- https://github.com/lxc/distrobuilder/blob/v3.4.0/generators/incus-agent.go

Changes adapt the module import path and agent names to LXD. The canonical
agent configuration-drive setup is preserved. Each compatibility fixture's
SHA256 is checked before patching an upstream builder.

The signature-test public key is the upstream fixture signer
`48D6A5F42D6057BF9A3780045DE8949A899C8D99`, obtained from
https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x5DE8949A899C8D99
including the historical signing subkey
`61F1F20D98671F25CA19887C993408D1137B7D51` used by the original 2018
fixtures. It contains only public material; expired fixture keys are never
used for production image verification.
Original positive, tampered-signature, missing-key, and wrong-key verification
assertions remain in place; tests import public fixtures without a keyserver.
Production image signature verification is unchanged.
