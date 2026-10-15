"""Filter Oracle's SELinux label at final SquashFS packing, after chroot unmounts."""
from pathlib import Path
import sys

MARKER = 'hosted-oracle-final-squashfs-labels'
PACK = '\t\t\t// Create rootfs as squashfs.\n'
CALL = '\t\t\terr = shared.RunCommand(l.ctx, nil, nil, "mksquashfs", args...)'
FILTER = '''\t\t\t// hosted-oracle-final-squashfs-labels
\t\t\t// /run is a temporary mount during hooks; only final packing sees
\t\t\t// its underlying ISO files. Keep other supported xattrs intact.
\t\t\tif l.definition.Image.Distribution == "oracle" {
\t\t\t\targs = append(args, "-xattrs-exclude", "^security[.]selinux$")
\t\t\t}

'''


def transform(source):
    if MARKER in source:
        if source.count(FILTER) != 1 or source.count(CALL) != 1:
            raise ValueError('Existing Oracle packing compatibility patch changed')
        return source
    if (source.count(PACK) != 1 or source.count(CALL) != 1
            or source.count('rootfsFile = filepath.Join(l.targetDir, "rootfs.squashfs")') != 1
            or 'func (l *' not in source or 'Build(unified bool, compression string, vm bool)' not in source):
        raise ValueError('Native container packing contract changed; revalidate the builder')
    return source.replace(PACK, FILTER + PACK, 1)


def patch(root):
    paths = [path for name in ('incus.go', 'lxd.go') if (path := root / 'image' / name).is_file()]
    if len(paths) != 1:
        raise ValueError('Expected exactly one native image packing source')
    path = paths[0]
    path.write_text(transform(path.read_text()))


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
