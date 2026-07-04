from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Department, Hospital


DEMO_DEPARTMENTS = (
    "General Medicine",
    "Cardiology",
    "Dermatology",
    "Neurology",
    "Orthopedics",
    "Pediatrics",
)

DEMO_HOSPITALS = (
    {
        "name": "Northstar Demo Hospital",
        "city": "Bengaluru",
        "address": "Fictional Demo Campus, Bengaluru",
        "registration_number": "MEDLOG-DEMO-BLR-001",
    },
    {
        "name": "Greenfield Demo Medical Centre",
        "city": "Pune",
        "address": "Fictional Demo Campus, Pune",
        "registration_number": "MEDLOG-DEMO-PUN-001",
    },
    {
        "name": "Horizon Demo Care Hospital",
        "city": "Hyderabad",
        "address": "Fictional Demo Campus, Hyderabad",
        "registration_number": "MEDLOG-DEMO-HYD-001",
    },
)


def ensure_demo_catalog(db: Session) -> tuple[int, int]:
    hospitals_created = 0
    departments_created = 0

    for details in DEMO_HOSPITALS:
        hospital = db.scalar(
            select(Hospital).where(
                Hospital.registration_number == details["registration_number"]
            )
        )
        if hospital is None:
            hospital = Hospital(**details, is_active=True)
            db.add(hospital)
            db.flush()
            hospitals_created += 1

        existing_departments = set(
            db.scalars(
                select(Department.name).where(Department.hospital_id == hospital.id)
            ).all()
        )
        for name in DEMO_DEPARTMENTS:
            if name not in existing_departments:
                db.add(
                    Department(
                        hospital_id=hospital.id,
                        name=name,
                        description=f"Demo {name.lower()} services",
                        is_active=True,
                    )
                )
                departments_created += 1

    db.commit()
    return hospitals_created, departments_created


def main() -> None:
    db = SessionLocal()
    try:
        hospitals_created, departments_created = ensure_demo_catalog(db)
        print(
            "Demo catalog ready: "
            f"{hospitals_created} hospitals and "
            f"{departments_created} departments created."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
