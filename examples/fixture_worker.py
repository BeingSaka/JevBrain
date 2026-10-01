"""Test fixture only. This is NOT an AI worker; never configure for production."""
import json
import sys
payload=json.load(sys.stdin)
assert 'original_request' in payload
print('Atlas launches on 15 October 2026. Price has not been announced.')
