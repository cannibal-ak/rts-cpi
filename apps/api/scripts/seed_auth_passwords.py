"""Verify canonical demo user passwords are seeded.

Migration 016 creates the 4 canonical users with bcrypt-hashed temporary
passwords directly. This script is now an IDEMPOTENT VERIFICATION TOOL:

  - Checks that each canonical user has a password_hash set
  - As a safety net, seeds the hash if somehow missing
  - Prints a summary table

Usage:
    docker compose exec api python scripts/seed_auth_passwords.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
from app.core.config import settings

CANONICAL_USERS = [
    ("admin@rts.com",      "admin123",   "rts"),
    ("jy@airline.com",     "airline123", "jy"),
    ("pw@airline.com",     "airline123", "pw"),
    ("fjl@cruise.com",     "cruise123",  "fjl"),
]

engine = create_engine(settings.database_url, pool_pre_ping=True)


def main():
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    results = []
    patched = 0

    with engine.connect() as conn:
        for email, temp_pw, expected_slug in CANONICAL_USERS:
            row = conn.execute(text(
                "SELECT u.id, u.password_hash, u.must_change_password, t.slug "
                "FROM app_user u JOIN tenant t ON t.id = u.tenant_id "
                "WHERE u.email = :email"
            ), {"email": email}).fetchone()

            if row is None:
                results.append((email, expected_slug, "MISSING USER", "N/A"))
                continue

            uid, pw_hash, must_change, slug = row

            if pw_hash:
                results.append((email, slug, "YES", str(must_change)))
                print(f"SKIP {email} — already seeded")
            else:
                # Safety net: seed if migration 016 somehow didn't set it
                h = pwd_ctx.hash(temp_pw)
                conn.execute(text(
                    "UPDATE app_user SET password_hash = :h, must_change_password = true "
                    "WHERE id = :uid"
                ), {"h": h, "uid": uid})
                results.append((email, slug, "SET (safety net)", "true"))
                patched += 1
                print(f"SET  {email} — password seeded (safety net)")

        if patched > 0:
            conn.commit()

    # Summary table
    print("\n" + "=" * 78)
    print("SEED AUTH PASSWORDS — Verification Summary")
    print("=" * 78)
    print(f"{'Email':<25} {'Tenant':<10} {'Hash Set':<20} {'Must Change'}")
    print("-" * 78)
    for email, slug, hash_status, must_change in results:
        print(f"{email:<25} {slug:<10} {hash_status:<20} {must_change}")
    print("=" * 78)
    print(f"Total: {len(results)} users checked, {patched} patched\n")

    # Exit code
    missing = sum(1 for r in results if r[2] == "MISSING USER")
    if missing:
        print(f"ERROR: {missing} canonical user(s) not found in database!")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
