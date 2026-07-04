from getpass import getpass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.role == UserRole.SUPER_ADMIN)):
            print("A super administrator already exists; no changes were made.")
            return

        full_name = input("Administrator full name: ").strip()
        raw_email = input("Administrator email: ").strip().lower()
        try:
            email = validate_email(raw_email, check_deliverability=False).normalized.lower()
        except EmailNotValidError as exc:
            raise SystemExit(f"Invalid email address: {exc}") from exc

        if len(full_name) < 2:
            raise SystemExit("Full name must contain at least two characters.")
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("That email address is already registered.")

        password = getpass("Strong password (12+ characters): ")
        confirmation = getpass("Confirm password: ")
        if len(password) < 12:
            raise SystemExit("Password must contain at least 12 characters.")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")

        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=UserRole.SUPER_ADMIN,
            )
        )
        db.commit()
        print("Super administrator created successfully.")


if __name__ == "__main__":
    main()
