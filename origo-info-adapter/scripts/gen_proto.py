"""Generate gRPC stubs from vendored StellarStation protos.

Run via `make proto`. Output is gitignored; regenerate after touching proto/.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "src" / "origo_info_adapter" / "_proto"


def main() -> int:
    protos = sorted(PROTO_DIR.rglob("*.proto"))
    if not protos:
        print(f"no .proto files under {PROTO_DIR}", file=sys.stderr)
        return 1

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        f"--pyi_out={OUT_DIR}",
        *(str(p) for p in protos),
    ]
    subprocess.run(cmd, check=True)

    # protoc emits absolute-style imports ("from stellarstation.api.v1 import ...").
    # Rewrite them to be relative to our _proto package so we don't collide with a
    # pip-installed `stellarstation` distribution and don't need sys.path games.
    _rewrite_imports(OUT_DIR)
    _add_init_files(OUT_DIR)
    print(f"generated {len(protos)} protos -> {OUT_DIR}")
    return 0


def _rewrite_imports(out: Path) -> None:
    pattern = re.compile(r"^from stellarstation", flags=re.MULTILINE)
    for py in out.rglob("*.py"):
        text = py.read_text()
        new = pattern.sub("from origo_info_adapter._proto.stellarstation", text)
        # grpc_python_out also emits `import stellarstation.api.v1.x_pb2 as ...`
        new = re.sub(
            r"^import stellarstation\.",
            "import origo_info_adapter._proto.stellarstation.",
            new,
            flags=re.MULTILINE,
        )
        if new != text:
            py.write_text(new)


def _add_init_files(out: Path) -> None:
    for d in [out, *(p for p in out.rglob("*") if p.is_dir())]:
        (d / "__init__.py").touch(exist_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())