import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/deploy_image_portal.sh'


class PortalDeploymentTests(unittest.TestCase):
    def deploy(self, results):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'timeout').write_text('''#!/bin/sh
count=$(cat "$COUNT" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$COUNT"
eval "result=\\${RESULT_$count}"
exit "$result"
''')
            (folder / 'sleep').write_text('#!/bin/sh\nexit 0\n')
            for name in ('timeout', 'sleep'):
                (folder / name).chmod(0o755)
            count = folder / 'count'
            environment = dict(os.environ, PATH=str(folder) + os.pathsep + os.environ['PATH'],
                               COUNT=str(count), NETLIFY_SITE_ID='fixture', NETLIFY_AUTH_TOKEN='fixture',
                               GITHUB_REPOSITORY='oneclickvirt/fixture', GITHUB_SHA='a' * 40)
            environment.update({f'RESULT_{i}': str(status) for i, status in enumerate(results, 1)})
            result = subprocess.run(['bash', str(SCRIPT)], env=environment, capture_output=True,
                                    text=True, timeout=10)
            return result, int(count.read_text())

    def test_a_stalled_attempt_can_retry_and_succeed(self):
        result, attempts = self.deploy([124, 0])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(attempts, 2)

    def test_persistent_timeouts_remain_failure(self):
        result, attempts = self.deploy([124, 124, 124])
        self.assertEqual(result.returncode, 124)
        self.assertEqual(attempts, 3)


if __name__ == '__main__':
    unittest.main()
