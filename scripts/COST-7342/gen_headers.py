# Print base64-encoded x-rh-identity headers for curl-based HTTP testing.
# Output format:  OLD_HEADER=<base64>  NEW_HEADER=<base64>
import base64
import json
import sys


def encode(identity: dict) -> str:
    return base64.b64encode(json.dumps(identity).encode()).decode()


def make_identity(account: str, org_id: str, username: str, email: str) -> dict:
    return {
        "identity": {
            "account_number": account,
            "org_id": org_id,
            "type": "User",
            "user": {"username": username, "email": email, "is_org_admin": True},
        },
        "entitlements": {"cost_management": {"is_entitled": True}},
    }


old = encode(make_identity("55555555", "11111111_test", "test-user-refresh", "test-user@example.com"))
new = encode(make_identity("66666666", "22222222_test", "test-user-refresh", "test-user@example.com"))

sys.stdout.write(f"OLD_HEADER={old}\n")
sys.stdout.write(f"NEW_HEADER={new}\n")
