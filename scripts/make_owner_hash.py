"""Generate a password hash for the private hosted dashboard."""

from getpass import getpass

from werkzeug.security import generate_password_hash


def main():
    first = getpass("Choose the hosted dashboard owner password: ")
    if len(first) < 14:
        raise SystemExit("Use a password with at least 14 characters.")
    second = getpass("Repeat the password: ")
    if first != second:
        raise SystemExit("The passwords did not match.")
    print("\nOWNER_PASSWORD_HASH value (store this only in Vercel environment variables):")
    print(generate_password_hash(first, method="scrypt"))


if __name__ == "__main__":
    main()
