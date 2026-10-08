"""Profile validation rules shared by the onboarding form and chat corrections."""

from datetime import date

EARLIEST_DOB = date(1900, 1, 1)


def validate_dob(dob: date) -> date:
    if dob > date.today():
        raise ValueError("Date of birth cannot be in the future.")
    if dob < EARLIEST_DOB:
        raise ValueError("Date of birth must be on or after 1900-01-01.")
    return dob
