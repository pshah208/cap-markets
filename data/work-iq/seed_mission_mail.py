"""Seed every mission thread without changing the hero-client importer's state.

Requires WORKIQ_TENANT_ID, WORKIQ_CLIENT_ID, WORKIQ_CLIENT_SECRET and
WORKIQ_USER_MAPPING_FILE. The private mapping must explicitly map all mission
personas, including the admin alias, and identify driver_alias.

    python seed_mission_mail.py [--dry-run] [--purge]
"""

import argparse

import seed_work_iq as s
from workiq_config import ConfigurationError, load_config


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--purge", action="store_true")
    args = ap.parse_args()
    try:
        config = load_config(
            "app", actions=("mail",), mail_source="mission_emails.json", source_dir=s.HERE,
        )
    except ConfigurationError as exc:
        ap.error(str(exc))
    g = s.Graph("app", dry_run=args.dry_run, config=config)
    s.seed_mail(g, purge=args.purge, source="mission_emails.json", all_clients=True)


if __name__ == "__main__":
    main()
