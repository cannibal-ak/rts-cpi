"""Seed temporary passwords for existing demo users.

Idempotent: skips users that already have a password_hash set.
Prints a summary table with temporary passwords for first-time login.

Usage:
    docker compose exec api python scripts/seed_auth_passwords.py
"""

import os
import sys
import secrets
import string

# Ensure app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import AppUser
from app.models.tenant import Tenant
from app.services.auth_service import hash_password

# Connect using superuser engine (not RLS)
engine = create_engine(settings.database_url, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def generate_temp_password(length: int = 16) -> str:
    """Generate a strong temporary password meeting all complexity rules."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure it meets all rules
        if (any(c.isupper() for c in pwd) and
            any(c.islower() for c in pwd) and
            any(c.isdigit() for c in pwd) and
            any(c in "!@#$%^&*" for c in pwd)):
            return pwd


def main():
    db = Session()
    try:
        users = db.query(AppUser).all()
        if not users:
            print("No users found in app_user table.")
            return

        results = []

        for user in users:
            tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
            tenant_slug = tenant.slug if tenant else "unknown"

            if user.password_hash:
                results.append((user.email, tenant_slug, "<already set>", user.must_change_password))
                continue

            temp_password = generate_temp_password()
            user.password_hash = hash_password(temp_password)
            user.must_change_password = True

            results.append((user.email, tenant_slug, temp_password, True))

        db.commit()

        # Print summary table
        print("\n" + "=" * 80)
        print("SEED AUTH PASSWORDS — Summary")
        print("=" * 80)
        print(f"{'Email':<30} {'Tenant':<10} {'Temp Password':<20} {'Must Change'}")
        print("-" * 80)
        for email, tenant_slug, pwd, must_change in results:
            print(f"{email:<30} {tenant_slug:<10} {pwd:<20} {must_change}")
        print("=" * 80)
        print(f"\nTotal users processed: {len(results)}")
        print("All users must change their password on first login.\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
