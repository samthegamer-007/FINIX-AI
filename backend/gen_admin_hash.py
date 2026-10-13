"""Run locally to create the value for ADMIN_n_PASSWORD_HASH:

    python gen_admin_hash.py

It prompts for a password (hidden) and prints the hash to paste into Render.
Never put the plain password in Render or in the repo."""
import getpass

from werkzeug.security import generate_password_hash

pw = getpass.getpass("Admin password: ")
if len(pw) < 12:
    raise SystemExit("Use at least 12 characters for an admin password.")
if pw != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords did not match.")
print("\nPaste this into the ADMIN_n_PASSWORD_HASH env var:\n")
print(generate_password_hash(pw))
