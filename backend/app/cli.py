"""Local administrative commands. Never run automatically on server startup."""
import argparse
from getpass import getpass
from pydantic import ValidationError
from sqlalchemy import select
from app.database import SessionLocal
from app.models import User, UserRole, AccountStatus
from app.schemas.auth import RegisterRequest
from app.services.catalogs import seed_catalogs
from app.utils.security import hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed-catalogs", "create-admin"])
    parser.add_argument("--name")
    parser.add_argument("--email")
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "seed-catalogs":
            seed_catalogs(db)
            print("Catalogs seeded; existing names retained.")
            return
        if not args.name or not args.email:
            parser.error("create-admin requires --name and --email")
        password = getpass("Admin password (8+ characters, letter and number): ")
        if getpass("Confirm password: ") != password:
            parser.error("Passwords do not match.")
        # Reuse existing identity/password validation without exposing public ADMIN registration.
        try:
            data = RegisterRequest(name=args.name, email=args.email, password=password, role="ALUMNI")
        except ValidationError as error:
            parser.error("; ".join(item["msg"] for item in error.errors(include_input=False)))
        email = str(data.email).lower()
        if db.scalar(select(User).where(User.email == email)):
            parser.error("Email already exists; no account was changed.")
        db.add(User(name=data.name, email=email, password_hash=hash_password(password),
                    role=UserRole.ADMIN, account_status=AccountStatus.ACTIVE))
        db.commit()
        print("Admin created. Log in through the normal login page.")


if __name__ == "__main__":
    main()
