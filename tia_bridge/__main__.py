import argparse
import json
import os
from pathlib import Path
import sys

from .errors import public_error
from .mcp import MCPServer
from .paths import local_root
from .service import Bridge


def main():
    parser = argparse.ArgumentParser(description="Local TIA Openness MCP bridge (stdio only).")
    parser.add_argument("--backend", choices=["openness", "mock"], default="openness")
    parser.add_argument("--project-root", required=True, help="Existing local directory of closed project subfolders.")
    parser.add_argument("--workspace", required=True, help="Separate private local directory for copies and staging.")
    parser.add_argument("--tia-version", type=int, choices=[19, 20], default=20, help="V20 documented target; V19 configurable but unverified.")
    parser.add_argument("--tia-api-dir", help="Trusted, installed Siemens PublicAPI directory.")
    parser.add_argument("--allow-writes", action="store_true", help="Allow import, compile and save in working copies.")
    parser.add_argument("--operation-timeout", type=int, default=240, choices=range(10, 601), metavar="10..600")
    args = parser.parse_args()
    try:
        projects = local_root(args.project_root)
        workspace = local_root(args.workspace, create=True)
        if args.backend == "mock":
            from .mock import MockBackend
            backend = MockBackend()
        else:
            from .openness import OpennessBackend
            api = args.tia_api_dir or str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) /
                        "Siemens" / "Automation" / f"Portal V{args.tia_version}" / "PublicAPI" / f"V{args.tia_version}")
            backend = OpennessBackend(api, args.tia_version, args.operation_timeout)
        bridge = Bridge(backend, projects, workspace, version=args.tia_version, allow_writes=args.allow_writes)
        MCPServer(bridge).serve(sys.stdin.buffer, sys.stdout.buffer)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    except Exception as exc:
        sys.stderr.write(json.dumps(public_error(exc)) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
