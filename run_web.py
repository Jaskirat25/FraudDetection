"""
run_web.py - Launcher for Aadhaar Authenticity Screening System Web Dashboard (M9).
Usage:
    python run_web.py [--port 8000] [--host 127.0.0.1]
"""

import sys
import argparse
from pathlib import Path
import uvicorn

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Aadhaar Screening Web Dashboard Launcher")
    parser.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable live auto-reload for development")
    args = parser.parse_args()

    print("\n=======================================================")
    print("  🚀 Layered Aadhaar Authenticity Screening Dashboard (M9)")
    print("=======================================================")
    print(f"  * Local Web Dashboard: http://{args.host}:{args.port}")
    print(f"  * API Docs (Swagger):  http://{args.host}:{args.port}/docs")
    print("  * Press Ctrl+C to terminate.")
    print("=======================================================\n")

    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
