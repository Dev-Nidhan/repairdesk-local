"""Create the fictional, read-only database used by the Render showcase."""

from pathlib import Path

from database import Database
from demo_data import load_demo_data

DEMO_DATABASE = Path(__file__).with_name("public_demo.db")


def main() -> None:
    database = Database(DEMO_DATABASE)
    added = load_demo_data(database)
    if added != 3:
        raise RuntimeError(
            f"Expected to prepare 3 fictional demo jobs; added {added}."
        )


if __name__ == "__main__":
    main()
