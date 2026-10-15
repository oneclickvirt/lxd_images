"""Repair known bootstrap source contracts before testing an upstream builder."""
import hashlib
from pathlib import Path
import sys


KEY_DIGEST = 'be8c4f070b696e64d8ce40e59a95a57e8b5c776f0015c2fd64e14b896622bdb4'


def oracle_source(source):
    if 'hosted-oracle-versioned-iso' in source:
        return source
    before = 'if s.definition.Image.Release == "9" {'
    if source.count(before) != 1:
        raise ValueError('Oracle ISO bootstrap contract changed; revalidate the builder')
    source = source.replace(before, '// hosted-oracle-versioned-iso\n\t\t\tif s.majorVersion == "8" || s.majorVersion == "9" || s.majorVersion == "10" {')
    for kind in ('boot', 'dvd'):
        before = f'fmt.Sprintf("OracleLinux-R9-U%d-%s-{kind}.iso", i, s.architecture)'
        after = f'fmt.Sprintf("OracleLinux-R%s-U%d-%s-{kind}.iso", s.majorVersion, i, s.architecture)'
        if source.count(before) != 1:
            raise ValueError('Oracle ISO filename contract changed; revalidate the builder')
        source = source.replace(before, after)
    return source


def rocky_source(source, key):
    if hashlib.sha256(key).hexdigest() != KEY_DIGEST:
        raise ValueError('Rocky 10 signing key integrity mismatch')
    if 'hosted-rocky10-signing-key' in source:
        return source
    before = 'mkdir -p /etc/yum.repos.d\nif [ -d /mnt/cdrom ]; then'
    if source.count(before) != 1:
        raise ValueError('Rocky bootstrap contract changed; revalidate the builder')
    # Supply the vendor release-10 key before either bootstrap repository is
    # configured. Older releases retain their existing signing keys.
    insertion = '''mkdir -p /etc/yum.repos.d
# hosted-rocky10-signing-key
if [ "${RELEASE}" = 10 ]; then
    mkdir -p /etc/pki/rpm-gpg
    cat <<'HOSTED_ROCKY_KEY' > /etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial
''' + key.decode().strip() + '''
HOSTED_ROCKY_KEY
    GPG_KEYS=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial
fi
if [ -d /mnt/cdrom ]; then'''
    return source.replace(before, insertion)


def main(root):
    oracle = root / 'sources/oraclelinux-http.go'
    rocky = root / 'sources/rocky-http.go'
    # Validate both transformations before replacing either source file.
    first = oracle_source(oracle.read_text())
    second = rocky_source(rocky.read_text(), Path(__file__).with_name('rocky-10.asc').read_bytes())
    oracle.write_text(first)
    rocky.write_text(second)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
