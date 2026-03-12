import argparse
import asyncio
from server.gateway import AgentGateway
from clients.cli.app import OClawCLI


def main():
    parser = argparse.ArgumentParser(description="OClaw Agent")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the backend server",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Start the CLI client",
    )
    args = parser.parse_args()

    if args.serve:
        server = AgentGateway()
        server.run()
    elif args.cli:
        cli = OClawCLI()
        asyncio.run(cli.run())


if __name__ == "__main__":
    main()
