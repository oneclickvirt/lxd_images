"""Export the real root partition UUID for OpenWrt's initramfs-free kernel."""
from pathlib import Path
import sys

MARKER = 'hosted-root-partuuid'
CONTEXT = '\t\tc.global.ctx = context.WithValue(c.global.ctx, shared.ContextKeyEnviron, []string{fmt.Sprintf("%s=%s", shared.EnvRootUUID, rootUUID)})'
ENVIRONMENT = '''\t\t// hosted-root-partuuid
\t\trootPartUUID, err := vm.findRootfsDevPARTUUID()
\t\tif err != nil {
\t\t\treturn fmt.Errorf("Failed to find rootfs partition UUID: %w", err)
\t\t}

\t\tc.global.ctx = context.WithValue(c.global.ctx, shared.ContextKeyEnviron, []string{
\t\t\tfmt.Sprintf("%s=%s", shared.EnvRootUUID, rootUUID),
\t\t\tfmt.Sprintf("LXD_IMAGEBUILDER_ROOT_PARTUUID=%s", rootPartUUID),
\t\t})'''
FINDER = '''
// hosted-root-partuuid
// OpenWrt boots without an initramfs, so its kernel needs PARTUUID rather
// than a filesystem UUID or the builder host's temporary loop device.
func (v *vm) findRootfsDevPARTUUID() (string, error) {
\tdevice := v.getRootfsDevFile()
\tif device == "" {
\t\treturn "", fmt.Errorf("Failed to get rootfs device name")
\t}

\tvar out strings.Builder
\tif err := shared.RunCommand(v.ctx, nil, &out, "blkid", "-o", "export", device); err != nil {
\t\treturn "", fmt.Errorf("Failed to get rootfs partition UUID: %w", err)
\t}

\tfor _, field := range strings.Fields(out.String()) {
\t\tif strings.HasPrefix(field, "PARTUUID=") && len(field) > len("PARTUUID=") {
\t\t\treturn field, nil
\t\t}
\t}

\treturn "", fmt.Errorf("No rootfs partition UUID found")
}
'''


def transform(main, vm):
    if MARKER in main or MARKER in vm:
        if main.count(ENVIRONMENT) != 1 or vm.count(FINDER) != 1:
            raise ValueError('Existing partition UUID compatibility patch changed')
        return main, vm
    if (main.count(CONTEXT) != 1 or main.count('rootUUID, err := vm.findRootfsDevUUID()') != 1
            or vm.count('func (v *vm) findRootfsDevUUID()') != 1
            or vm.count('func (v *vm) getRootfsDevFile() string') != 1
            or '"strings"' not in vm):
        raise ValueError('VM partition UUID source contract changed; revalidate the builder')
    return main.replace(CONTEXT, ENVIRONMENT), vm + FINDER


def patch(root):
    main = root / 'lxd-imagebuilder/main_lxd.go'
    vm = root / 'lxd-imagebuilder/vm.go'
    updated_main, updated_vm = transform(main.read_text(), vm.read_text())
    main.write_text(updated_main)
    vm.write_text(updated_vm)
    fixture = Path(__file__).with_name('fixtures') / 'lxd-vm-partuuid-test.go.txt'
    (vm.parent / 'hosted_partuuid_test.go').write_text(fixture.read_text())


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
