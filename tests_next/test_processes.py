import os
import subprocess
import sys

import pytest

from pacoca.processes import ProcessJob


@pytest.mark.skipif(os.name!='nt',reason='Windows Job Object')
def test_engine_job_terminates_its_child_on_close():
    job=ProcessJob()
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert job.handle
        job.attach(process)
        job.close()
        process.wait(timeout=5)
        assert process.returncode is not None
    finally:
        if process.poll() is None:
            process.kill();process.wait()
