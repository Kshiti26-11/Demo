"""Generate Python gRPC stubs for the Orders contract and fix protoc's absolute import.

Usage: uv run python scripts/gen_proto.py [PROTO_FILE] [OUT_DIR]
Defaults: contracts/orders.proto -> orders_service/gen
"""
import re
import sys
from pathlib import Path

import grpc_tools
from grpc_tools import protoc


def generate(proto: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").write_text("")
    include = Path(grpc_tools.__file__).parent / "_proto"
    rc = protoc.main([
        "grpc_tools.protoc",
        f"-I{proto.parent}",
        f"-I{include}",
        f"--python_out={out_dir}",
        f"--grpc_python_out={out_dir}",
        f"--pyi_out={out_dir}",
        str(proto),
    ])
    if rc != 0:
        raise SystemExit(f"protoc failed with exit code {rc}")
    grpc_file = out_dir / f"{proto.stem}_pb2_grpc.py"
    text = grpc_file.read_text()
    fixed = re.sub(rf"^import {proto.stem}_pb2 as ", f"from . import {proto.stem}_pb2 as ", text, flags=re.M)
    if fixed == text:
        raise SystemExit(f"expected 'import {proto.stem}_pb2 as' in {grpc_file}; protoc output changed")
    grpc_file.write_text(fixed)
    print(f"generated {out_dir} from {proto}")


if __name__ == "__main__":
    proto = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("contracts/orders.proto")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("orders_service/gen")
    generate(proto, out)
