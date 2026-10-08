"""Sun-sign stub: fixed date ranges, no real astrology calculation."""

from datetime import date

# The (month, day) on which each sign begins, in calendar order.
SIGN_START_DATES = [
    (1, 20, "Aquarius"),
    (2, 19, "Pisces"),
    (3, 21, "Aries"),
    (4, 20, "Taurus"),
    (5, 21, "Gemini"),
    (6, 21, "Cancer"),
    (7, 23, "Leo"),
    (8, 23, "Virgo"),
    (9, 23, "Libra"),
    (10, 23, "Scorpio"),
    (11, 22, "Sagittarius"),
    (12, 22, "Capricorn"),
]


def sun_sign_for(dob: date) -> str:
    # 1–19 January still belongs to Capricorn, which began on 22 December.
    sign = "Capricorn"
    for month, day, name in SIGN_START_DATES:
        if (dob.month, dob.day) >= (month, day):
            sign = name
    return sign
