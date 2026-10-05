"""Local operator account provisioning; passwords never enter command arguments."""
import argparse
import getpass
from regswarm import auth, db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-user"])
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=["admin", "reviewer", "analyst"], default="reviewer")
    args = parser.parse_args()
    password = getpass.getpass("Password (at least 14 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords did not match")
    con = db.connect()
    try:
        auth.provision(con, args.username, args.name, password, args.role)
    finally:
        con.close()
    print("Account created. Sign in to RegSwarm.")


if __name__ == "__main__":
    main()
