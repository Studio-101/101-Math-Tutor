import os
import sys
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = PROJECT_ROOT / "scratch"

def execute_python_code(code_str: str, timeout_sec: int = 15) -> tuple[bool, str]:
    """
    Executes a Python code snippet locally in a safe subprocess without permission prompts.
    Captures stdout and stderr.
    
    Returns:
        (success: bool, output: str)
    """
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SCRATCH_DIR / "verify_temp.py"
    
    try:
        temp_file.write_text(code_str, encoding="utf-8")
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(temp_file)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        
        output = proc.stdout
        if proc.stderr:
            output += ("\n[STDERR]\n" + proc.stderr)
            
        success = (proc.returncode == 0)
        return success, output.strip()
        
    except subprocess.TimeoutExpired:
        return False, f"Error: Code execution timed out after {timeout_sec} seconds."
    except Exception as e:
        return False, f"Error executing script: {str(e)}"
    finally:
        # Keep the latest scratch file for debugging if needed, or clean up if desired
        pass
