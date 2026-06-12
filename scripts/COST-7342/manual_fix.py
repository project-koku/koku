# Apply the manual runbook fix (Option A): rename the old user so its username
# is freed up for the new identity on the next request.
# Handles the case where "old-<username>" already exists by appending a counter.
from api.iam.models import User

USERNAME = "test-user-refresh"

old_user = User.objects.filter(username=USERNAME).first()
if not old_user:
    print(f"No user with username {USERNAME!r} — nothing to rename.")
else:
    new_username = f"old-{USERNAME}"
    counter = 1
    while User.objects.filter(username=new_username).exists():
        new_username = f"old-{USERNAME}-{counter}"
        counter += 1
    old_user.username = new_username
    old_user.save()
    print(f"[OK] Renamed {USERNAME!r} -> {new_username!r}")
    print(f"     Username {USERNAME!r} is now free for the new identity.")
