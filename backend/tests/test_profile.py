"""Onboarding form, GET /users/me, the sun-sign stub and the zodiac link."""

from datetime import date, timedelta

import pytest

from app.main import app
from app.profile.sun_sign import sun_sign_for
from tests.conftest import VALID_PROFILE, BrokenNeo4jDriver, signup


async def zodiac_links() -> list[str]:
    """Names of every Zodiac node any user is linked to."""
    records, _, _ = await app.state.neo4j.execute_query(
        "MATCH (:User)-[:HAS_ZODIAC]->(z:Zodiac) RETURN z.name AS name"
    )
    return [record["name"] for record in records]


# --- sun-sign stub ---


@pytest.mark.parametrize(
    "dob, expected",
    [
        (date(1995, 8, 15), "Leo"),
        (date(1995, 7, 22), "Cancer"),  # last day of Cancer
        (date(1995, 7, 23), "Leo"),  # first day of Leo
        (date(1995, 8, 23), "Virgo"),
        (date(2000, 1, 1), "Capricorn"),  # start of the year
        (date(2000, 1, 19), "Capricorn"),
        (date(2000, 1, 20), "Aquarius"),
        (date(2000, 12, 21), "Sagittarius"),
        (date(2000, 12, 22), "Capricorn"),  # end of the year
        (date(2000, 12, 31), "Capricorn"),
        (date(2000, 2, 29), "Pisces"),  # leap day
        (date(2000, 3, 21), "Aries"),
    ],
)
def test_sun_sign_for_date(dob, expected):
    assert sun_sign_for(dob) == expected


# --- GET /users/me ---


async def test_me_for_a_new_user_has_no_profile(client):
    headers = await signup(client)

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"email": "rahul@example.com", "profile_complete": False, "profile": None}


# --- PUT /users/me/profile ---


async def test_saving_the_profile_stores_it_and_links_the_sun_sign(client):
    headers = await signup(client)

    response = await client.put("/users/me/profile", json=VALID_PROFILE, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["profile_complete"] is True
    assert body["email"] == "rahul@example.com"
    assert body["profile"] == {
        "name": "Rahul",
        "dob": "1995-08-15",
        "birth_time": "14:30:00",
        "birth_time_known": True,
        "birth_place": "Delhi",
        "language": "en",
        "profile_updated_via": "form",
        "zodiac": {"name": "Leo", "element": "Fire", "traits": ["confident", "generous", "expressive"]},
    }
    # GET returns the same thing, and login now reports the profile as complete.
    assert (await client.get("/users/me", headers=headers)).json() == body
    login = await client.post("/auth/login", json={"email": "rahul@example.com", "password": "correct-horse"})
    assert login.json()["profile_complete"] is True


async def test_sun_sign_sent_by_the_user_is_ignored(client):
    headers = await signup(client)

    response = await client.put(
        "/users/me/profile", json={**VALID_PROFILE, "zodiac": "Pisces", "sun_sign": "Pisces"}, headers=headers
    )

    assert response.json()["profile"]["zodiac"]["name"] == "Leo"


async def test_changing_the_dob_moves_the_single_zodiac_link(client):
    headers = await signup(client)
    await client.put("/users/me/profile", json=VALID_PROFILE, headers=headers)

    response = await client.put(
        "/users/me/profile", json={**VALID_PROFILE, "dob": "1995-03-25"}, headers=headers
    )

    assert response.json()["profile"]["zodiac"]["name"] == "Aries"
    assert await zodiac_links() == ["Aries"]  # exactly one link; the Leo link is gone


async def test_saving_the_same_profile_twice_changes_nothing(client):
    headers = await signup(client)

    first = await client.put("/users/me/profile", json=VALID_PROFILE, headers=headers)
    second = await client.put("/users/me/profile", json=VALID_PROFILE, headers=headers)

    assert first.json() == second.json()
    assert await zodiac_links() == ["Leo"]


async def test_unknown_birth_time_is_stored_as_unknown(client):
    headers = await signup(client)

    # A time sent together with "I don't know" is dropped.
    response = await client.put(
        "/users/me/profile", json={**VALID_PROFILE, "birth_time_known": False}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["profile"]["birth_time_known"] is False
    assert response.json()["profile"]["birth_time"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"name": "   "},
        {"birth_place": ""},
        {"dob": (date.today() + timedelta(days=1)).isoformat()},
        {"dob": "1899-12-31"},
        {"dob": "not-a-date"},
        {"language": "hi"},
        {"birth_time": None},  # birth_time_known is true but no time given
        {"birth_time_known": None},
    ],
)
async def test_invalid_profile_is_rejected(client, change):
    headers = await signup(client)

    response = await client.put("/users/me/profile", json={**VALID_PROFILE, **change}, headers=headers)

    assert response.status_code == 422
    assert (await client.get("/users/me", headers=headers)).json()["profile_complete"] is False


async def test_missing_required_field_is_rejected(client):
    headers = await signup(client)
    without_place = {key: value for key, value in VALID_PROFILE.items() if key != "birth_place"}

    response = await client.put("/users/me/profile", json=without_place, headers=headers)

    assert response.status_code == 422


async def test_profile_requires_a_token(client):
    assert (await client.put("/users/me/profile", json=VALID_PROFILE)).status_code == 401


# --- isolation between users ---


async def test_each_user_sees_only_their_own_profile(client):
    rahul = await signup(client, "rahul@example.com")
    priya = await signup(client, "priya@example.com")
    await client.put("/users/me/profile", json=VALID_PROFILE, headers=rahul)

    # A user_id in the body is ignored: the user always comes from the token.
    await client.put(
        "/users/me/profile",
        json={**VALID_PROFILE, "name": "Priya", "dob": "1998-03-25", "user_id": "someone-else"},
        headers=priya,
    )

    rahul_me = (await client.get("/users/me", headers=rahul)).json()
    priya_me = (await client.get("/users/me", headers=priya)).json()
    assert rahul_me["profile"]["name"] == "Rahul"
    assert rahul_me["profile"]["zodiac"]["name"] == "Leo"
    assert priya_me["profile"]["name"] == "Priya"
    assert priya_me["profile"]["zodiac"]["name"] == "Aries"


# --- store failures ---


async def test_profile_save_returns_503_when_neo4j_is_down(client):
    headers = await signup(client)
    # Signup needs Neo4j, so it is only taken down afterwards.
    real_driver = app.state.neo4j
    app.state.neo4j = BrokenNeo4jDriver()
    try:
        response = await client.put("/users/me/profile", json=VALID_PROFILE, headers=headers)
    finally:
        app.state.neo4j = real_driver

    assert response.status_code == 503
    # Neo4j is written first, so the Postgres flag was never set.
    assert (await client.get("/users/me", headers=headers)).json()["profile_complete"] is False
