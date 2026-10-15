"""Final packing must handle attributes hidden by build-time tmpfs mounts."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import patch_container_labels as labels


SOURCE = '''package image
func (l *IncusImage) Build(unified bool, compression string, vm bool) (string, string, error) {
        if vm {
            err = shared.Copy(qcowImage, rootfsFile)
        } else {
\t\t\trootfsFile = filepath.Join(l.targetDir, "rootfs.squashfs")
\t\t\targs := []string{l.sourceDir, rootfsFile, "-noappend"}
\t\t\t// Create rootfs as squashfs.
\t\t\terr = shared.RunCommand(l.ctx, nil, nil, "mksquashfs", args...)
        }
}
'''


class FinalContainerLabelTests(unittest.TestCase):
    def test_filter_is_oracle_only_and_stays_in_the_non_vm_packing_branch(self):
        before, _ = SOURCE.split('        } else {', 1)
        for kind in ('IncusImage', 'LXDImage'):
            source = SOURCE.replace('IncusImage', kind)
            result = labels.transform(source)
            self.assertEqual(result.split('        } else {', 1)[0], before.replace('IncusImage', kind))
            self.assertIn('if l.definition.Image.Distribution == "oracle" {', result)
            self.assertIn('"-xattrs-exclude", "^security[.]selinux$"', result)
            self.assertNotIn('-no-xattrs', result)
            self.assertLess(result.index('rootfs.squashfs'), result.index(labels.MARKER))
            self.assertLess(result.index(labels.MARKER), result.index('"mksquashfs"'))

    def test_reapplying_the_builder_patch_is_idempotent(self):
        result = labels.transform(SOURCE)
        self.assertEqual(labels.transform(result), result)

    def test_changed_builder_contract_is_rejected(self):
        for source in (SOURCE.replace('"mksquashfs"', '"other"'), SOURCE + SOURCE,
                       SOURCE.replace('rootfs.squashfs', 'disk.qcow2')):
            with self.assertRaises(ValueError):
                labels.transform(source)


if __name__ == '__main__':
    unittest.main()
