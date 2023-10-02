# Putting it top-level, as pytest will search parent directories for `conftest.py`


from common.config import ENV


def pytest_sessionstart(session):
    assert ENV in (
        "local",
        "test",
    ), "Tests should only run in 'local' or 'test' environments. Current ENV: {}".format(
        ENV
    )
