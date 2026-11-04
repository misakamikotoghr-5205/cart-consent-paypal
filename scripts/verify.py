"""Local reproducible verification; no PayPal or model service is contacted."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
    with tempfile.TemporaryDirectory() as temp:
        result = subprocess.run([sys.executable, '-m', 'cart_consent', '--db', str(Path(temp) / 'demo.sqlite3'), 'demo'],
            cwd=ROOT, env=os.environ | {'CART_PAYMENT_MODE': 'mock', 'CART_AGENT_MODE': 'mock'},
            capture_output=True, text=True, check=True)
        evidence = json.loads(result.stdout)
        assert evidence['unapproved_blocked'] and evidence['address_change_revoked_approval'] and evidence['new_approval_new_order']
        assert evidence['capture_implemented'] is False and evidence['ai_used'] is False
    print('Local consent, mutation, HTTP role and official adapter contract checks passed. No remote payment or model inference was performed.')


if __name__ == '__main__':
    main()
