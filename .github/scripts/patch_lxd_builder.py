"""Repair known bootstrap source contracts before testing an upstream builder."""
import hashlib
from pathlib import Path
import sys


KEY_DIGEST = 'be8c4f070b696e64d8ce40e59a95a57e8b5c776f0015c2fd64e14b896622bdb4'
COMPATIBILITY_FIXTURES = {
    'openwrt-combined-http.go.txt': 'a6f1841f1341cbbbf397fca5f55596b891e27630c6f7ae4c7de55d297aa25e05',
    'lxd-procd-agent.go.txt': 'abef9ad81e40d7c9b36a7564b8f46699ee3802abecb2e715f4df0f69a3cd3144',
}


def fixture(name):
    payload = Path(__file__).with_name('fixtures').joinpath(name).read_bytes()
    if hashlib.sha256(payload).hexdigest() != COMPATIBILITY_FIXTURES[name]:
        raise ValueError('OpenWrt compatibility fixture integrity mismatch')
    return payload.decode()


def openwrt_source(source):
    if 'unpackCombinedImg(' in source:
        return source
    if (source.count('func (s *openwrt) Run() error') != 1
            or 'shared.Unpack(filepath.Join(fpath, fname), s.rootfsDir)' not in source):
        raise ValueError('OpenWrt source contract changed; revalidate the builder')
    # Use the signed official combined EFI image, as distrobuilder 3.4 does.
    # A rootfs tarball lacks the EFI loader required by VM consumers.
    return '// hosted-openwrt-combined-efi\n' + fixture('openwrt-combined-http.go.txt')


def openwrt_agent(source):
    if 'func (g *lxdAgent) handleProcd() error' in source:
        return source
    before = '\n\tif fi.Mode()&os.ModeSymlink != 0 {'
    if (source.count(before) != 1 or source.count('func (g *lxdAgent) RunLXD(') != 1):
        raise ValueError('OpenWrt agent contract changed; revalidate the builder')
    dispatch = '''
    // hosted-openwrt-procd-agent
    if _, err := os.Stat(filepath.Join(g.sourceDir, "etc", "openwrt_version")); err == nil {
        return g.handleProcd()
    }
'''
    return source.replace(before, dispatch + before) + '\n' + fixture('lxd-procd-agent.go.txt')


def arch_release_test(source):
    if 'hosted-arch-release-fixture' in source:
        return source
    if (source.count('func TestArchLinuxGetLatestRelease(t *testing.T)') != 1
            or source.count('src.getLatestRelease("https://archive.archlinux.org/iso/", "x86_64")') != 1):
        raise ValueError('Arch release parser test changed; revalidate the builder')
    initialize = 'src := &archlinux{}\n\t\t\tsrc.client = http.DefaultClient' if 'src.client = http.DefaultClient' in source else 'var src archlinux'
    # Exercise the actual parser and HTTP client without letting an unrelated
    # vendor archive outage block every distribution's builder installation.
    return '''package sources

import (
    "net/http"
    "net/http/httptest"
    "testing"

    "github.com/stretchr/testify/require"
)

// hosted-arch-release-fixture
func TestArchLinuxGetLatestRelease(t *testing.T) {
    for _, test := range []struct {
        name string
        body string
        status int
        want string
    }{
        {"unsorted releases", `<a href="2026.09.01/">2026.09.01/</a><a href="invalid/">invalid/</a><a href="2026.10.01/">2026.10.01/</a><a href="2025.12.01/">2025.12.01/</a>`, 200, "2026.10.01"},
        {"empty index", `<a href="../">../</a>`, 200, ""},
        {"upstream error", "unavailable", 503, ""},
    } {
        t.Run(test.name, func(t *testing.T) {
            server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
                w.WriteHeader(test.status)
                _, _ = w.Write([]byte(test.body))
            }))
            defer server.Close()
            ''' + initialize + '''
            release, err := src.getLatestRelease(server.URL, "x86_64")
            if test.want == "" {
                require.Error(t, err)
                return
            }
            require.NoError(t, err)
            require.Equal(t, test.want, release)
        })
    }
}
'''


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
    arch_test = root / 'sources/archlinux-http_test.go'
    # Validate every transformation before replacing any source file.
    first = oracle_source(oracle.read_text())
    second = rocky_source(rocky.read_text(), Path(__file__).with_name('rocky-10.asc').read_bytes())
    third = arch_release_test(arch_test.read_text())
    openwrt = root / 'sources/openwrt-http.go'
    agent = root / 'generators/lxd-agent.go'
    fourth = openwrt_source(openwrt.read_text())
    fifth = openwrt_agent(agent.read_text())
    oracle.write_text(first)
    rocky.write_text(second)
    arch_test.write_text(third)
    openwrt.write_text(fourth)
    agent.write_text(fifth)
    source_tests = Path(__file__).with_name('fixtures') / 'openwrt-hosted-source_test.go.txt'
    agent_tests = Path(__file__).with_name('fixtures') / 'openwrt-hosted-agent_test.go.txt'
    (root / 'sources/hosted_openwrt_test.go').write_text(source_tests.read_text())
    (root / 'generators/hosted_openwrt_test.go').write_text(agent_tests.read_text())


if __name__ == '__main__':
    main(Path(sys.argv[1]))
