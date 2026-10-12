import subprocess
import sys

import pytest

from video_qc.media import run_command


def test_media_child_cancellation():
    with pytest.raises(KeyboardInterrupt):
        run_command([sys.executable, "-c", "import time; time.sleep(20)"], cancelled=lambda: True)


def test_media_child_error_details():
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_command([sys.executable, "-c", "import sys; print('media error', file=sys.stderr); sys.exit(2)"])
    assert error.value.returncode == 2
    assert "media error" in error.value.stderr
