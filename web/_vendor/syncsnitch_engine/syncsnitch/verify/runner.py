import os
from pathlib import Path
import subprocess


class Runner:
    def run(
        self,
        args: list[str],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 900,
    ) -> tuple[int, str]:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        try:
            res = subprocess.run(
                args,
                cwd=cwd,
                env=run_env,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            out = (res.stdout or "") + (res.stderr or "")
            return res.returncode, out
        except subprocess.TimeoutExpired as e:
            out = ((e.stdout or "") + (e.stderr or "")) if hasattr(e, "stdout") else "Timeout expired"
            return 124, out
        except Exception as e:
            return 1, str(e)
