"""Fail if this feature modifies tracked files outside online/."""
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
BASE = 'd89f8657062ac2bd3f5675a20e661d52acbba7b6'

def main():
    changed = subprocess.check_output(['git','diff','--name-only',BASE,'--'],cwd=ROOT,text=True).splitlines()
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    outside = sorted({path for path in changed+untracked if not path.startswith('online/')})
    if outside:
        raise SystemExit('Out-of-scope changes:\n'+'\n'.join(outside))
    print('PASS: every changed or new source file is under online/.')
    print('Original PC/Web/core/assets/entrypoints/dependencies match '+BASE+'.')

if __name__ == '__main__': main()
