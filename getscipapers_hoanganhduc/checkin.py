import argparse
from . import ablesci, wosonhj

def checkin_ablesci():
    ablesci.check_in()

def checkin_wosonhj():
    wosonhj.checkin_wosonhj()

SERVICES = {
    'ablesci': checkin_ablesci,
    'wosonhj': checkin_wosonhj,
}

def main():
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'checkin'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} checkin"

    parser = argparse.ArgumentParser(
        prog=program_name,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Check in to one or more supported services.",
        epilog="Examples:\n"
               "  %(prog)s ablesci\n"
               "  %(prog)s wosonhj\n"
               "  %(prog)s all\n"
               "  %(prog)s ablesci wosonhj"
    )
    parser.add_argument(
        'services',
        nargs='+',
        choices=list(SERVICES.keys()) + ['all'],
        help="List of services to check in to (choose from: %(choices)s, or 'all')"
    )
    args = parser.parse_args()

    if 'all' in args.services:
        for func in SERVICES.values():
            func()
    else:
        for service in args.services:
            SERVICES[service]()

if __name__ == "__main__":
    main()