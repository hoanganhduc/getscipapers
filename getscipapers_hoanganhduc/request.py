import argparse
import os
from . import getpapers, nexus, ablesci, wosonhj, facebook, scinet
import asyncio

SERVICE_LIST = ["nexus", "ablesci", "wosonhj", "facebook", "scinet"]

def extract_dois_from_text_input(text):
    """
    Extract a list of DOIs from the given text input using getpapers.extract_dois_from_text.
    """
    return getpapers.extract_dois_from_text(text)

def request_dois(dois, verbose=False, service=None):
    """
    Post DOI numbers to one or more services and ask for help obtaining the papers.
    If service is a list, aggregate results from all specified services.
    If service is "all", use all available services.
    """
    if isinstance(dois, str):
        dois = [dois]
    results = {}

    # Allow service to be a string or a list of strings
    if service is None:
        service_list = ["nexus"]
    elif isinstance(service, str):
        if service.lower() == "all":
            service_list = SERVICE_LIST
        else:
            service_list = [service]
    else:
        # If "all" is in the list, use all services
        if any(s.lower() == "all" for s in service):
            service_list = SERVICE_LIST
        else:
            service_list = list(service)

    for svc in service_list:
        svc_results = {}
        if svc == "nexus":
            async def fetch_nexus(dois):
                try:
                    response = await nexus.request_papers_by_doi_list(dois)
                    if verbose:
                        print("📨 Posted DOIs to Nexus bot for help.")
                    return {doi: response.get(doi, {"error": "No response or not found"}) for doi in dois}
                except Exception as e:
                    if verbose:
                        print(f"❌ Failed to post DOIs to Nexus: {e}")
                    return {doi: {"error": str(e)} for doi in dois}
            svc_results = asyncio.run(fetch_nexus(dois))
        elif svc == "ablesci":
            try:
                response_list = ablesci.request_multiple_dois(dois)
                if verbose:
                    print("📨 Posted DOIs to AbleSci for help.")
                # Map results by DOI for consistency with other services
                svc_results = {}
                for item in response_list:
                    doi = item.get('doi')
                    if item.get('success'):
                        svc_results[doi] = {"success": True}
                    else:
                        svc_results[doi] = {"error": item.get('error', 'Unknown error')}
                # Ensure all DOIs are present in the result
                for doi in dois:
                    if doi not in svc_results:
                        svc_results[doi] = {"error": "No response or not found"}
            except Exception as e:
                if verbose:
                    print(f"❌ Failed to post DOIs to AbleSci: {e}")
                svc_results = {doi: {"error": str(e)} for doi in dois}
        elif svc == "wosonhj":
            try:
                response = wosonhj.request_multiple_dois(dois)
                if verbose:
                    print("📨 Posted DOIs to Wosonhj for help.")
                svc_results = {doi: response.get(doi, {"error": "No response or not found"}) for doi in dois}
            except Exception as e:
                if verbose:
                    print(f"❌ Failed to post DOIs to Wosonhj: {e}")
                svc_results = {doi: {"error": str(e)} for doi in dois}
        elif svc == "facebook":
            try:
                response = facebook.request_multiple_dois(dois)
                if verbose:
                    print("📨 Posted DOIs to Facebook for help.")
                svc_results = {doi: response.get(doi, {"error": "No response or not found"}) for doi in dois}
            except Exception as e:
                if verbose:
                    print(f"❌ Failed to post DOIs to Facebook: {e}")
                svc_results = {doi: {"error": str(e)} for doi in dois}
        elif svc == "scinet":
            try:
                response = scinet.login_and_request_multiple_dois_simple(dois)
                if verbose:
                    print("📨 Posted DOIs to SciNet for help.")
                svc_results = {doi: response.get(doi, {"error": "No response or not found"}) for doi in dois}
            except Exception as e:
                if verbose:
                    print(f"❌ Failed to post DOIs to SciNet: {e}")
                svc_results = {doi: {"error": str(e)} for doi in dois}
        else:
            raise ValueError(f"Service '{svc}' is not supported.")

        # Merge results: nest by service if multiple, else flat dict
        for doi in dois:
            if len(service_list) == 1:
                results[doi] = svc_results.get(doi, {"error": "No response or not found"})
            else:
                if doi not in results:
                    results[doi] = {}
                results[doi][svc] = svc_results.get(doi, {"error": "No response or not found"})

    return results

def parse_doi_argument(doi_arg):
    """
    Parse the --doi argument, which can be:
    - a single DOI string
    - a comma/semicolon/space separated list of DOIs
    - a text string containing DOIs
    - a path to a text file containing DOIs or text
    Returns a list of DOIs.
    """
    # Check if it's a file path
    if os.path.isfile(doi_arg):
        with open(doi_arg, "r", encoding="utf-8") as f:
            text = f.read()
        return extract_dois_from_text_input(text)
    # Try to extract DOIs directly
    # If it looks like a list (comma/semicolon/space separated)
    if any(sep in doi_arg for sep in [",", ";", " "]):
        # Try to extract DOIs from the string
        return extract_dois_from_text_input(doi_arg)
    # Otherwise, treat as a single DOI or text
    dois = extract_dois_from_text_input(doi_arg)
    if dois:
        return dois
    # If nothing found, return as single element list
    return [doi_arg]

def parse_service_argument(service_arg):
    """
    Parse the --service argument, which can be:
    - "all" (case-insensitive)
    - a single service string
    - a comma/semicolon/space separated list of services
    Returns a list of valid services or "all".
    """
    if service_arg is None:
        return ["nexus"]
    if isinstance(service_arg, list):
        services = service_arg
    else:
        # Split by comma, semicolon, or space
        for sep in [",", ";"]:
            if sep in service_arg:
                services = [s.strip() for s in service_arg.split(sep)]
                break
        else:
            services = service_arg.split()
    # Handle "all" (case-insensitive)
    if any(s.lower() == "all" for s in services):
        return "all"
    # Filter only valid services
    valid_services = [svc for svc in services if svc in SERVICE_LIST]
    if not valid_services:
        raise ValueError(f"No valid services found in input: {service_arg}")
    return valid_services

def print_result_with_icons(doi, data):
    if isinstance(data, dict) and "error" in data:
        print(f"❌ DOI: {doi}\n   Error: {data['error']}\n")
    else:
        print(f"✅ DOI: {doi}\n   Result: {data}\n")

def main():
    """
    Main function for testing request_dois functionality.
    """
    # Get the parent package name from the module's __name__
    parent_package = __name__.split('.')[0] if '.' in __name__ else None

    if parent_package is None:
        program_name = 'request'
    elif '_' in parent_package:
        # If the parent package has an underscore, strip it
        parent_package = parent_package[:parent_package.index('_')]
        program_name = f"{parent_package} request"

    service_list_str = ", ".join(SERVICE_LIST)
    parser = argparse.ArgumentParser(
        prog=program_name,
        description="Post DOI requests to one or more services to ask for published papers.",
        epilog=(
            "Examples:\n"
            "  %(prog)s --doi 10.1000/xyz123\n"
            "  %(prog)s --doi '10.1000/xyz123,10.1000/abc456' --service nexus,ablesci\n"
            "  %(prog)s --doi mydois.txt --service wosonhj scinet\n"
            "  %(prog)s --doi 'Here are some DOIs: 10.1000/xyz123 10.1000/abc456' --service facebook\n"
            "  %(prog)s --doi '10.1000/xyz123' --service all\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--doi",
        required=True,
        help="A DOI, a list of DOIs, a text string, or a text file containing DOIs."
    )
    parser.add_argument(
        "--service",
        default="nexus",
        help=f"Service(s) to use for requesting DOIs (comma, semicolon, space separated, or 'all'). Available: {service_list_str}"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output."
    )
    args = parser.parse_args()

    dois = parse_doi_argument(args.doi)
    if not dois:
        print("⚠️  No valid DOIs found in the input.")
        return

    # Parse the service argument using the updated function
    services = parse_service_argument(args.service)
    result = request_dois(dois, verbose=args.verbose, service=services)
    for doi, data in result.items():
        print_result_with_icons(doi, data)

if __name__ == "__main__":
    main()