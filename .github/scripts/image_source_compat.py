"""Apply compatibility fixes after every upstream definition refresh."""
from pathlib import Path
import re
from append_image_actions import serialize, normalize_el_boot
from verify_image_definitions import verify
from image_ssh_identity import BUILD_HOOK

NATIVE_IMAGE_ARCHIVES = True


def openwrt_vm_root(document):
    """Reject empty boot roots instead of silently producing an unbootable VM."""
    hooks = [entry for entry in document.get('actions', [])
             if entry.get('types') == ['vm'] and '/boot/efi/' in entry['action']
             and 'ROOT_PARTUUID' in entry['action']]
    if len(hooks) != 2:
        raise ValueError('OpenWrt VM boot hook contract changed')
    for entry in hooks:
        action = entry['action']
        if 'hosted-openwrt-root-partuuid' in action:
            continue
        rootvar = ('LXD_IMAGEBUILDER_ROOT_PARTUUID' if 'LXD_IMAGEBUILDER_ROOT_PARTUUID' in action
                   else 'DISTROBUILDER_ROOT_PARTUUID')
        action = action.removeprefix('#!/bin/sh\n')
        entry['action'] = '''#!/bin/sh
set -eu
# hosted-openwrt-root-partuuid
guest_root=${ROOT_VARIABLE}
case "$guest_root" in PARTUUID=?*) ;; *) echo 'Expected root partition UUID' >&2; exit 1;; esac
case "${guest_root#PARTUUID=}" in *[!0-9a-fA-F-]*) echo 'Invalid root partition UUID' >&2; exit 1;; esac
'''.replace('ROOT_VARIABLE', rootvar) + action + '''
grep -Eq "(^|[[:space:]])root=${guest_root}([[:space:]]|$)" "$target"
'''


def instance_identity(document):
    actions = document.setdefault('actions', [])
    actions[:] = [entry for entry in actions if 'hosted-instance-ssh-identity' not in entry['action']]
    for entry in actions:
        entry['action'] = entry['action'].replace('    ssh-keygen -A || true\n', '').replace('ssh-keygen -A || true\n', '')
        entry['action'] = entry['action'].replace('    /usr/sbin/sshd || true\n', '').replace('/usr/sbin/sshd || true\n', '')
    actions.append({'trigger': 'post-files', 'action': BUILD_HOOK})


def vm_storage_drivers(document):
    """Build guest initramfs independently of a loop-backed build host."""
    drivers = {'path': '/etc/dracut.conf.d/50-hosted-storage.conf',
               'generator': 'dump', 'types': ['vm'],
               'content': 'hostonly="no"\nadd_drivers+=" virtio_scsi virtio_blk virtio_pci virtio_console sd_mod ext4 "\n'}
    files = document.setdefault('files', [])
    if drivers not in files:
        files.append(drivers)


def rocky_download_budget(document):
    """Let DNF switch slow mirrors before a large firmware exhausts the build."""
    # CLI flags affect only image construction, leaving guest DNF policy and
    # upstream mirror lists/signature verification intact.
    options = ['--setopt=minrate=262144', '--setopt=timeout=30', '--setopt=retries=3']
    for entry in document.get('packages', {}).get('sets', []):
        if entry.get('action') == 'install':
            flags = entry.setdefault('flags', [])
            for option in options:
                if option not in flags:
                    flags.append(option)


def ubuntu_arm_device_budget(document):
    """Keep EFI mandatory while ARM software emulation coldplugs devices."""
    # Jammy's older systemd does not support DefaultDeviceTimeoutSec.
    # Keep the override scoped to the release with the observed coldplug fault.
    config = {'path': '/etc/systemd/system.conf.d/50-image-arm-devices.conf',
              'generator': 'dump', 'types': ['vm'], 'architectures': ['arm64'],
              'releases': ['resolute'],
              'content': '[Manager]\nDefaultDeviceTimeoutSec=180s\n'}
    files = document.setdefault('files', [])
    files[:] = [entry for entry in files if entry.get('path') != config['path']]
    files.append(config)


UBUNTU_GROW_ROOT = r'''#!/bin/sh
set -eu
# Resolve the mounted root instead of assuming a SCSI bus or partition number.
root=$(readlink -f "$(findmnt -n -o SOURCE /)")
case "$root" in /dev/*) ;; *) echo 'Root is not a block device' >&2; exit 1;; esac
[ "$(findmnt -n -o FSTYPE /)" = ext4 ] || { echo 'Expected an ext4 root' >&2; exit 1; }
[ "$(lsblk -dn -o TYPE "$root")" = part ] || { echo 'Expected a plain root partition' >&2; exit 1; }
parent=$(lsblk -dn -o PKNAME "$root")
part=$(cat "/sys/class/block/${root##*/}/partition")
case "$parent" in ''|*/*|*[!a-zA-Z0-9_.-]*) echo 'Invalid root disk' >&2; exit 1;; esac
case "$part" in ''|*[!0-9]*) echo 'Invalid root partition number' >&2; exit 1;; esac
[ "$part" -gt 0 ]
if output=$(growpart "/dev/$parent" "$part" 2>&1); then
  printf '%s\n' "$output"
else
  status=$?
  printf '%s\n' "$output"
  # growpart uses exit 1 for the normal case on subsequent boots.
  if [ "$status" -ne 1 ] || ! printf '%s\n' "$output" | grep -q '^NOCHANGE:'; then
    exit "$status"
  fi
fi
resize2fs "$root"
'''


def ubuntu_vm_compat(document):
    """Keep netplan's renderer enabled and grow the actual ext4 root device."""
    actions = document.setdefault('actions', [])
    for entry in actions:
        if ('growpart /dev/sda 2' not in entry['action']
                and 'hosted-ubuntu-root-growth' not in entry['action']):
            continue
        match = re.search(r'/etc/systemd/system/((?:incus|lxd)-growpart)\.service', entry['action'])
        if not match or entry.get('types') != ['vm']:
            raise ValueError('Ubuntu root growth hook contract changed')
        service = match[1]
        entry['action'] = '''#!/bin/sh
set -eu
# hosted-ubuntu-root-growth
install -d /usr/local/sbin
cat << 'IMAGE_GROW_ROOT' > /usr/local/sbin/image-grow-root
''' + UBUNTU_GROW_ROOT + '''IMAGE_GROW_ROOT
chmod 0755 /usr/local/sbin/image-grow-root
cat << 'IMAGE_GROW_SERVICE' > /etc/systemd/system/SERVICE_NAME.service
[Unit]
Description=Grow the mounted ext4 root partition
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/image-grow-root

[Install]
WantedBy=multi-user.target
IMAGE_GROW_SERVICE
systemctl enable SERVICE_NAME.service
'''.replace('SERVICE_NAME', service)
    network = {'trigger': 'post-packages', 'types': ['vm'],
               'releases': ['noble', 'resolute'], 'action': '''#!/bin/sh
set -eu
# hosted-ubuntu-vm-networkd
# A generated netplan file still needs its renderer to start on every boot.
systemctl enable systemd-networkd.service
'''}
    for index, entry in enumerate(actions):
        if 'hosted-ubuntu-vm-networkd' in entry['action']:
            actions[index] = network
            break
    else:
        actions.append(network)


def rpm_vm_compat(document, distro):
    """Keep EL firmware, BLS entries and the actual root partition in sync."""
    vm_storage_drivers(document)
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    for entry in sets:
        if 'architectures' in entry:
            entry['architectures'] = ['aarch64' if arch == 'aaarch64' else arch
                                      for arch in entry['architectures']]
        entry['packages'] = ['grub2-efi-aa64' if package == 'grub2-efi-aarch64' else package
                             for package in entry.get('packages', [])]
    required = {'packages': ['grub2-tools', 'grubby'], 'action': 'install', 'types': ['vm']}
    if not any({key: value for key, value in entry.items() if key != 'flags'} == required
               for entry in sets):
        sets.append(required)
    # CentOS's upstream ARM selector omits EL9/EL10 entirely.
    if distro == 'centos':
        required = {'packages': ['grub2-efi-aa64'], 'action': 'install',
                    'types': ['vm'], 'architectures': ['aarch64'],
                    'releases': ['9-Stream', '10-Stream']}
        if not any({key: value for key, value in entry.items() if key != 'flags'} == required
                   for entry in sets):
            sets.append(required)
    actions = document.setdefault('actions', [])
    rootvar = ('LXD_IMAGEBUILDER_ROOT_UUID' if any('LXD_IMAGEBUILDER_ROOT_UUID' in a['action']
                                                for a in actions) else 'DISTROBUILDER_ROOT_UUID')
    # These images have EFI + one root partition; /boot is on that root.
    # RPM assumes a separate /boot in both the firmware prefix and BLS paths.
    action = r"""#!/bin/sh
set -eu
# hosted-rpm-efi-forwarder
guest_root=${DISTROBUILDER_ROOT_UUID}
case "$guest_root" in UUID=*) guest_uuid=${guest_root#UUID=};; *) echo 'Expected UUID root device' >&2; exit 1;; esac
test -n "$guest_uuid"
mkdir -p /boot/grub2 /boot/loader/entries
if [ ! -s /boot/grub2/grub.cfg ]; then
  test -s /boot/efi/EFI/VENDOR/grub.cfg
  cp /boot/efi/EFI/VENDOR/grub.cfg /boot/grub2/grub.cfg
fi
test -s /boot/grub2/grub.cfg
entries=0
for entry in /boot/loader/entries/*.conf; do
  [ -f "$entry" ] || continue
  # RPM may record the builder host's mount prefix in a BLS entry.
  # Resolve kernel/initramfs basenames against the guest's actual /boot;
  # the existence gate below still rejects missing or unexpected images.
  awk -v guest_root="$guest_root" '
    $1 == "options" {
      # BLS can carry a literal build-time loop device. kernelopts alone
      # cannot correct it; retain vendor options and replace every root=.
      printf "options"
      serial=0; armserial=0
      for (i=2; i<=NF; i++) {
        if ($i ~ /^root=/) continue
        if ($i ~ /^console=ttyS0(,|$)/) serial=1
        if ($i ~ /^console=ttyAMA0(,|$)/) armserial=1
        printf " %s", $i
      }
      printf " root=%s", guest_root
      if (!serial) printf " console=ttyS0"
      if (!armserial) printf " console=ttyAMA0"
      printf "\n"
      next
    }
    $1 == "linux" || $1 == "initrd" {
      for (i=2; i<=NF; i++) {
        name=$i; sub(/^.*\//, "", name)
        if (name ~ /^(vmlinuz-|initramfs-)/) $i="/boot/" name
      }
    }
    { print }
  ' "$entry" > "$entry.hosted"
  cat "$entry.hosted" > "$entry"
  rm "$entry.hosted"
  for image_path in $(awk '$1 == "linux" || $1 == "initrd" {for (i=2; i<=NF; i++) print $i}' "$entry"); do
    test -s "$image_path" || { echo "Missing BLS boot image: $image_path" >&2; exit 1; }
  done
  entries=$((entries + 1))
done
if grep -q 'blscfg' /boot/grub2/grub.cfg; then
  test "$entries" -gt 0
  if [ ! -s /boot/grub2/grubenv ]; then grub2-editenv /boot/grub2/grubenv create; fi
  grub2-editenv /boot/grub2/grubenv set blsdir=/boot/loader/entries
  grub2-editenv /boot/grub2/grubenv set "kernelopts=root=$guest_root ro console=tty1 console=ttyS0 console=ttyAMA0"
fi
for vendor in VENDOR BOOT; do
  mkdir -p "/boot/efi/EFI/$vendor"
  cat > "/boot/efi/EFI/$vendor/grub.cfg" <<EOF
search --no-floppy --fs-uuid --set=dev $guest_uuid
set prefix=(\$dev)/boot/grub2
export prefix
configfile \$prefix/grub.cfg
EOF
done
""".replace('DISTROBUILDER_ROOT_UUID', rootvar).replace('VENDOR', {
        'almalinux': 'almalinux', 'centos': 'centos', 'rockylinux': 'rocky', 'fedora': 'fedora'}[distro])
    hook = {'trigger': 'post-files', 'types': ['vm'], 'action': action}
    if distro != 'fedora':
        hook['releases'] = ['9-Stream', '10-Stream'] if distro == 'centos' else ['9', '10']
    for index, entry in enumerate(actions):
        if 'hosted-rpm-efi-forwarder' in entry['action']:
            actions[index] = hook
            break
    else:
        actions.append(hook)
    keys = {'trigger': 'post-files', 'types': ['vm'], 'action': r"""#!/bin/sh
set -eu
# hosted-rpm-ssh-hostkeys
mkdir -p /etc/systemd/system/sshd.service.d
cat > /etc/systemd/system/hosted-ssh-hostkeys.service <<'UNIT'
[Unit]
Description=Generate missing SSH host keys before SSH starts
After=local-fs.target
Before=sshd.service
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
RemainAfterExit=yes
UNIT
cat > /etc/systemd/system/sshd.service.d/10-host-keys.conf <<'UNIT'
[Unit]
Requires=hosted-ssh-hostkeys.service
After=hosted-ssh-hostkeys.service
UNIT
"""}
    if keys not in actions:
        actions.append(keys)
    if distro == 'fedora':
        # Fedora's 45-second device deadline expires while ARM TCG is still
        # coldplugging devices. Keep EFI mandatory, with a finite allowance
        # for software virtualization rather than accepting emergency mode.
        devices = {'trigger': 'post-files', 'types': ['vm'], 'architectures': ['aarch64'],
                   'action': r'''#!/bin/sh
set -eu
# hosted-fedora-arm-device-deadline
mkdir -p /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/50-image-arm-devices.conf <<'CONF'
[Manager]
DefaultDeviceTimeoutSec=180s
CONF
'''}
        if devices not in actions:
            actions.append(devices)



def raw_cloud_compat(document):
    """Undo the LXC generator's deliberate cloud-init disablement for cloud images."""
    hook = {'trigger': 'post-files', 'types': ['container'], 'variants': ['cloud'],
            'action': r"""#!/bin/sh
set -eu
# hosted-raw-cloud-enable
rm -f /etc/cloud/cloud-init.disabled
if command -v systemctl >/dev/null 2>&1; then
  for unit in cloud-init-local cloud-init cloud-init-main cloud-config cloud-final; do
    if [ -f "/usr/lib/systemd/system/$unit.service" ] || [ -f "/lib/systemd/system/$unit.service" ]; then
      systemctl enable "$unit.service"
    fi
  done
elif command -v rc-update >/dev/null 2>&1; then
  for service in cloud-init-local cloud-init cloud-config cloud-final; do
    if [ -x "/etc/init.d/$service" ]; then rc-update add "$service" default; fi
  done
else
  echo 'Cloud image has no supported cloud-init service manager' >&2
  exit 1
fi
"""}
    actions = document.setdefault('actions', [])
    if hook not in actions:
        actions.append(hook)


def normalize(root):
    path = root / 'images_yaml/debian.yaml'
    document = verify(path.read_text())
    # Cloud generators remove build-time host keys. Debian's ssh.service
    # tests the configuration before it generates keys, so regenerate at
    # each first boot before that test without shipping shared host keys.
    ssh_hook = {'trigger': 'post-files', 'action': r"""#!/bin/sh
set -eu
# hosted-debian-ssh-hostkeys
mkdir -p /etc/systemd/system/ssh.service.d
printf '[Service]\nExecStartPre=\nExecStartPre=/usr/bin/ssh-keygen -A\nExecStartPre=/usr/sbin/sshd -t\n' > /etc/systemd/system/ssh.service.d/10-host-keys.conf
rm -f /etc/ssh/sshd_not_to_be_run
systemctl enable ssh.service
"""}
    if ssh_hook not in document.setdefault('actions', []):
        document['actions'].append(ssh_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/fedora.yaml'
    document = verify(path.read_text())
    # fedora-http expects Koji's /packages tree, not the release ISO directory.
    document['source']['url'] = 'https://kojipkgs.fedoraproject.org'
    for entry in document.get('actions', []):
        # Current Fedora bootstrap rootfs does not contain this tool until
        # the systemd package transaction has completed.
        if entry['trigger'] == 'post-unpack' and 'systemd-machine-id-setup' in entry['action']:
            entry['trigger'] = 'post-packages'
    path.write_text(serialize(document))

    path = root / 'images_yaml/openwrt.yaml'
    document = verify(path.read_text())
    # The combined EFI downloader uses the vendor target/subtarget names.
    # The builder's named architecture maps do not include OpenWrt.
    document['mappings'] = {'architectures': {'amd64': 'x86-64', 'x86_64': 'x86-64',
                                              'arm64': 'armsr-armv8', 'aarch64': 'armsr-armv8'}}
    # Upstream APK definitions no longer have the old '- sudo' insertion anchor.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    existing = {p for s in sets if s.get('action') == 'install' and not s.get('types')
                for p in s.get('packages', [])}
    missing = [p for p in ['curl', 'ca-bundle', 'openssh-server', 'openssh-keygen', 'bash'] if p not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
    openwrt_vm_root(document)
    path.write_text(serialize(document))

    path = root / 'images_yaml/archlinux.yaml'
    document = verify(path.read_text())
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    # ARM's rootfs is now minimal; retaining an upstream removal block also
    # removed openssh/libedit after installation. Keep runtime dependencies.
    for entry in sets:
        if entry.get('action') == 'remove':
            entry['packages'] = [p for p in entry['packages'] if p not in ['openssh', 'libedit']]
    sets[:] = [s for s in sets if s.get('packages')]
    if not any('openssh' in s['packages'] and s.get('action')=='install' and not s.get('architectures') for s in sets):
        sets.append({'packages': ['openssh'], 'action': 'install'})
    # Regional official mirrors allow pacman to recover from a stalled CDN
    # endpoint without changing package signature verification.
    mirror_hook = {'trigger': 'post-unpack', 'architectures': ['aarch64'], 'action': """#!/bin/sh
set -eu
# hosted-arm-mirror-fallback
cat > /etc/pacman.d/mirrorlist <<'MIRRORS'
Server = https://ca.us.mirror.archlinuxarm.org/$arch/$repo
Server = https://de3.mirror.archlinuxarm.org/$arch/$repo
MIRRORS
"""}
    actions = document.setdefault('actions', [])
    if mirror_hook not in actions:
        # Configure mirrors before the upstream pacman-keyring bootstrap hook.
        actions.insert(0, mirror_hook)
    rootvar = ('LXD_IMAGEBUILDER_ROOT_UUID' if any('LXD_IMAGEBUILDER_ROOT_UUID' in a['action']
                                                for a in actions) else 'DISTROBUILDER_ROOT_UUID')
    initramfs = {'trigger': 'post-files', 'types': ['vm'], 'architectures': ['aarch64'],
                'action': r'''#!/bin/sh
set -eu
# hosted-arch-arm-initramfs
test -s /boot/initramfs-linux.img
case "${DISTROBUILDER_ROOT_UUID}" in UUID=?*) ;; *) echo 'Expected UUID root device' >&2; exit 1;; esac
if ! grep -Fq '# hosted-arm-initramfs-selection' /etc/default/grub; then
  cat >> /etc/default/grub <<'CONF'

# hosted-arm-initramfs-selection
GRUB_EARLY_INITRD_LINUX_CUSTOM="${GRUB_EARLY_INITRD_LINUX_CUSTOM:+${GRUB_EARLY_INITRD_LINUX_CUSTOM} }initramfs-linux.img"
CONF
fi
# The vendor hook generates grub.cfg before mkinitcpio and GRUB does not
# automatically associate ARM's unversioned Image with initramfs-linux.img.
grub-mkconfig -o /boot/grub/grub.cfg
sed "s#root=[^ ]*#root=${DISTROBUILDER_ROOT_UUID}#g" /boot/grub/grub.cfg > /boot/grub/grub.cfg.hosted
cat /boot/grub/grub.cfg.hosted > /boot/grub/grub.cfg
rm /boot/grub/grub.cfg.hosted
grep -Eq '^[[:space:]]*initrd[[:space:]].*/initramfs-linux\.img([[:space:]]|$)' /boot/grub/grub.cfg
'''.replace('DISTROBUILDER_ROOT_UUID', rootvar)}
    for index, entry in enumerate(actions):
        if 'hosted-arch-arm-initramfs' in entry['action']:
            actions[index] = initramfs
            break
    else:
        actions.append(initramfs)
    path.write_text(serialize(document))

    path = root / 'images_yaml/gentoo.yaml'
    document = verify(path.read_text())
    # The old sudo anchor is now app-admin/sudo. Install runtime capabilities
    # independently of textual anchors and enable the selected init system.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    for entry in sets:
        if ('app-admin/syslog-ng' in entry.get('packages', [])
                and entry.get('variants') == ['openrc']):
            # The cloud variant uses the same OpenRC boot hook.
            entry['variants'] = ['openrc', 'cloud']
    existing = {p for s in sets if s.get('action') == 'install' and not s.get('types')
                for p in s.get('packages', [])}
    missing = [p for p in ['net-misc/openssh', 'net-misc/curl', 'app-misc/ca-certificates'] if p not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
    for entry in document.get('actions', []):
        if 'sshd_config' in entry['action']:
            entry['variants'] = ['cloud', 'openrc', 'systemd']
        if entry.get('types') == ['vm'] and entry.get('variants') == ['openrc']:
            entry['variants'] = ['openrc', 'cloud']
    efi_hook = {'trigger': 'post-unpack', 'types': ['vm'], 'variants': ['openrc', 'cloud'],
                'action': """#!/bin/sh
set -eu
# hosted-gentoo-efi-platform
mkdir -p /etc/portage/package.use
printf 'sys-boot/grub grub_platforms_efi-64\\n' > /etc/portage/package.use/hosted-grub
"""}
    if efi_hook not in document.setdefault('actions', []):
        document['actions'].insert(0, efi_hook)
    action = {'trigger': 'post-files', 'action': """#!/bin/sh
set -eu
# hosted-gentoo-runtime-ssh-keys
command -v sshd >/dev/null
command -v ssh-keygen >/dev/null
# Both packaged Gentoo init systems generate absent keys before sshd starts.
# Never distribute a key inherited from the stage3 rootfs or a build hook.
rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub /etc/ssh/ssh_host_*_key-cert.pub
if command -v rc-update >/dev/null 2>&1; then
  rc-update add sshd default
elif command -v systemctl >/dev/null 2>&1; then
  systemctl enable sshd
else
  echo 'Unsupported Gentoo init system' >&2
  exit 1
fi
"""}
    for index, entry in enumerate(document['actions']):
        if ('hosted-gentoo-runtime-ssh-keys' in entry['action'] or
                'command -v sshd >/dev/null\nssh-keygen -A\nif command -v rc-update' in entry['action']):
            document['actions'][index] = action
            break
    else:
        document['actions'].append(action)
    path.write_text(serialize(document))

    path = root / 'images_yaml/almalinux.yaml'
    document = verify(path.read_text())
    # Upstream's aaarch64 typo silently omitted grub2-efi-aarch64 for ARM VMs.
    for entry in document.get('packages', {}).get('sets', []):
        # Alma's BaseOS packages use aa64 for EFI on ARM in EL8/EL9/EL10.
        entry['packages'] = ['grub2-efi-aa64' if package == 'grub2-efi-aarch64' else package
                             for package in entry.get('packages', [])]
        if 'architectures' in entry:
            entry['architectures'] = ['aarch64' if arch == 'aaarch64' else arch
                                      for arch in entry['architectures']]
    for entry in document.get('actions', []):
        if 'hosted-compatible-bls' in entry['action']:
            entry['action'] = entry['action'].replace('\n  grub2-mkconfig -o "${target}"\nfi', '\nfi')
        if 'Track down the kernel' not in entry['action'] or 'hosted-el10-kernel' in entry['action']:
            continue
        before = 'kernel_path=$(find /boot -name "vmlinuz-${kver}" || true)'
        if before not in entry['action']:
            raise ValueError('unexpected EL10 kernel discovery hook')
        replacement = """# hosted-el10-kernel: kernel-core now keeps the RPM image under /usr/lib/modules.
if [ ! -s "/boot/vmlinuz-${kver}" ]; then
  for candidate in "/usr/lib/modules/${kver}/vmlinuz" "/lib/modules/${kver}/vmlinuz"; do
    if [ -s "$candidate" ]; then
      cp "$candidate" "/boot/vmlinuz-${kver}"
      break
    fi
  done
fi
kernel_path=$(find /boot -name "vmlinuz-${kver}" || true)"""
        entry['action'] = entry['action'].replace(before, replacement)
        # ARM guests use PL011 serial; retain x86's ttyS0 too.
        entry['action'] = entry['action'].replace('console=tty1 console=ttyS0', 'console=tty1 console=ttyS0 console=ttyAMA0')
    path.write_text(serialize(document))

    path = root / 'images_yaml/opensuse.yaml'
    document = verify(path.read_text())
    # Upstream removed vim-minimal, so legacy text insertion no longer adds
    # the default variant's SSH server or certificate-verifying HTTP client.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    existing = {package for entry in sets if entry.get('action') == 'install'
                and not any(entry.get(key) for key in ('types', 'variants', 'releases', 'architectures'))
                for package in entry.get('packages', [])}
    missing = [package for package in ('openssh-server', 'curl', 'ca-certificates')
               if package not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
    # New SUSE packages keep vendor SSH defaults under /usr/etc. Install the
    # mutable config before repository customization hooks edit it.
    ssh_hook = {'trigger': 'post-packages', 'action': """#!/bin/sh
set -eu
# hosted-suse-ssh-defaults
if [ ! -s /etc/ssh/sshd_config ] && [ -s /usr/etc/ssh/sshd_config ]; then
  mkdir -p /etc/ssh
  cp /usr/etc/ssh/sshd_config /etc/ssh/sshd_config
fi
mkdir -p /etc/systemd/system/sshd.service.d
printf '[Service]\\nExecStartPre=/usr/bin/ssh-keygen -A\\n' > /etc/systemd/system/sshd.service.d/10-host-keys.conf
systemctl enable sshd
"""}
    actions = document.setdefault('actions', [])
    for entry in actions:
        # The local stage renders DHCP configuration before networkd starts.
        # Enabling only cloud-init.service leaves Leap 16's NIC unmanaged.
        entry['action'] = entry['action'].replace(
            'systemctl enable cloud-init.service cloud-config.service cloud-final.service',
            'systemctl enable cloud-init-local.service cloud-init.service cloud-config.service cloud-final.service')
    for index, entry in enumerate(actions):
        if 'hosted-suse-ssh-defaults' in entry['action']:
            actions[index] = ssh_hook
            break
    else:
        actions.append(ssh_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/oracle.yaml'
    document = verify(path.read_text())
    # Oracle's ISO rootfs retains Anaconda's installer default.target. SSH
    # can be enabled yet never started because multi-user.target is absent
    # from that boot transaction. Select the normal installed-system target.
    target_hook = {'trigger': 'post-packages', 'action': """#!/bin/sh
set -eu
# hosted-oracle-runtime-target
systemctl set-default multi-user.target
"""}
    if target_hook not in document.setdefault('actions', []):
        document['actions'].append(target_hook)
    if NATIVE_IMAGE_ARCHIVES:
        # Oracle's ISO carries SELinux labels on links, files and directories.
        # An unprivileged Ubuntu container cannot restore any of these labels.
        # Strip only that attribute; retain capabilities, ACLs and file data.
        # Container policy is enforced by the host; VM labels stay intact.
        label_hook = {'trigger': 'post-files', 'types': ['container'], 'action': r'''#!/bin/sh
set -eu
# hosted-oracle-container-labels
find / -xdev -exec sh -ec '
  for path do
    if getfattr -h -n security.selinux -- "$path" >/dev/null 2>&1; then
      setfattr -h -x security.selinux -- "$path"
    fi
  done
' sh {} +
'''}
        labels = []
        replaced = False
        for entry in document['actions']:
            if any(marker in entry['action'] for marker in
                   ('hosted-oracle-symlink-labels', 'hosted-oracle-container-labels')):
                if not replaced:
                    labels.append(label_hook)
                    replaced = True
            else:
                labels.append(entry)
        if not replaced:
            labels.append(label_hook)
        document['actions'] = labels
    path.write_text(serialize(document))

    path = root / 'images_yaml/centos.yaml'
    document = verify(path.read_text())
    stale_mirror = 'https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/'
    canonical_mirror = 'https://mirror.stream.centos.org/'

    def replace_mirror(value):
        if isinstance(value, str):
            return value.replace(stale_mirror, canonical_mirror)
        if isinstance(value, list):
            return [replace_mirror(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_mirror(item) for key, item in value.items()}
        return value

    for entry in document.get('actions', []):
        entry['action'] = replace_mirror(entry['action'])
    packages = document.setdefault('packages', {})
    repositories = packages.get('repositories', [])
    packages['repositories'] = replace_mirror(repositories)
    path.write_text(serialize(document))

    for path in (root / 'images_yaml').glob('*.yaml'):
        if path.stem in ('almalinux', 'centos', 'rockylinux', 'fedora'):
            normalize_el_boot(path)
        document = verify(path.read_text())
        if path.stem == 'openeuler':
            # Verified against the vendor's current aarch64 RPM catalog.
            for entry in document.get('packages', {}).get('sets', []):
                entry['packages'] = ['grub2-efi-aa64' if p == 'grub2-efi-aarch64' else p
                                     for p in entry.get('packages', [])]
        if path.stem in ('almalinux', 'centos', 'rockylinux', 'fedora', 'openeuler'):
            # Current kernel-core packages can keep their bootable image in
            # /usr/lib/modules, while the VM hooks expect it under /boot.
            kernel_hook = {'trigger': 'post-packages', 'types': ['vm'], 'action': """#!/bin/sh
set -eu
# hosted-rpm-kernel-image
mkdir -p /boot
for modules in /usr/lib/modules/* /lib/modules/*; do
  [ -d "$modules" ] || continue
  version=${modules##*/}
  if [ -s "$modules/vmlinuz" ] && [ ! -s "/boot/vmlinuz-$version" ]; then
    cp "$modules/vmlinuz" "/boot/vmlinuz-$version"
  fi
done
"""}
            if kernel_hook not in document.setdefault('actions', []):
                document['actions'].append(kernel_hook)
        if path.stem in ('almalinux', 'centos', 'rockylinux', 'fedora'):
            rpm_vm_compat(document, path.stem)
        if path.stem in ('openeuler', 'opensuse'):
            vm_storage_drivers(document)
        if path.stem == 'rockylinux':
            rocky_download_budget(document)
        if path.stem == 'ubuntu':
            ubuntu_arm_device_budget(document)
            ubuntu_vm_compat(document)
        if not NATIVE_IMAGE_ARCHIVES and any(entry.get('generator') == 'cloud-init'
                                               for entry in document.get('files', [])):
            raw_cloud_compat(document)
        for entry in document.get('actions', []):
            entry['action'] = entry['action'].replace('PubkeyAuthentication no', 'PubkeyAuthentication yes')
        # /run is recreated at boot. Dangling resolvers in SUSE and older
        # Ubuntu images prevent the consumer from writing a DNS template
        # before start. Keep DHCP policy and a writable resolver target.
        dns_hook = {'trigger': 'post-files', 'types': ['container'], 'action': """#!/bin/sh
set -eu
# hosted-consumer-dns-file
if [ -L /etc/resolv.conf ]; then
  case "$(readlink /etc/resolv.conf)" in
    /run/*|../run/*|/var/run/*|../var/run/*)
      rm /etc/resolv.conf
      touch /etc/resolv.conf
      ;;
  esac
fi
"""}
        actions = document.setdefault('actions', [])
        if NATIVE_IMAGE_ARCHIVES:
            # Native archives rely on their DHCP resolver service and its live
            # symlink. An empty file disconnects resolved/netconfig/dhcpcd.
            # Raw LXC consumers instead receive DNS from their provisioner.
            actions[:] = [entry for entry in actions
                          if 'hosted-consumer-dns-file' not in entry['action']]
            instance_identity(document)
            path.write_text(serialize(document))
            continue
        for index, entry in enumerate(actions):
            if 'hosted-consumer-dns-file' in entry['action']:
                actions[index] = dns_hook
                break
        else:
            actions.append(dns_hook)
        instance_identity(document)
        path.write_text(serialize(document))
