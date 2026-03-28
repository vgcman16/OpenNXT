from __future__ import annotations

import argparse
import http.server
import json
import ssl
import tempfile
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_PFX = WORKSPACE / "data" / "tls" / "localhost.pfx"
DEFAULT_TARGET = "http://127.0.0.1:8080/jav_config.ws"


@dataclass(frozen=True)
class ProxyConfig:
    target_base_url: str


def build_target_url(target_base_url: str, request_path: str) -> str:
    parsed_base = urllib.parse.urlsplit(target_base_url)
    parsed_request = urllib.parse.urlsplit(request_path)
    query = parsed_request.query
    path = parsed_request.path or parsed_base.path or "/"
    return urllib.parse.urlunsplit(
        (
            parsed_base.scheme,
            parsed_base.netloc,
            path,
            query,
            "",
        )
    )


def export_pfx_to_temp_pem_files(pfx_path: Path, password: str) -> tuple[str, str]:
    key, cert, chain = pkcs12.load_key_and_certificates(pfx_path.read_bytes(), password.encode("utf-8"))
    if key is None or cert is None:
        raise RuntimeError(f"Unable to load private key and certificate from {pfx_path}")

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    if chain:
        for extra in chain:
            cert_pem += extra.public_bytes(serialization.Encoding.PEM)

    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    cert_handle = tempfile.NamedTemporaryFile("wb", delete=False, suffix=".pem")
    key_handle = tempfile.NamedTemporaryFile("wb", delete=False, suffix=".key")
    cert_handle.write(cert_pem)
    cert_handle.flush()
    key_handle.write(key_pem)
    key_handle.flush()
    cert_handle.close()
    key_handle.close()
    return cert_handle.name, key_handle.name


class JavConfigProxyHandler(http.server.BaseHTTPRequestHandler):
    server_version = "OpenNXTJavConfigProbe/1.0"

    def do_GET(self) -> None:  # noqa: N802
        config: ProxyConfig = self.server.proxy_config  # type: ignore[attr-defined]
        if not self.path.startswith("/jav_config.ws"):
            self.send_error(404, "Not Found")
            return

        target_url = build_target_url(config.target_base_url, self.path)
        with urllib.request.urlopen(target_url, timeout=10.0) as response:
            payload = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type", "text/plain; charset=iso-8859-1")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        entry = {
            "client": self.client_address[0],
            "message": format % args,
        }
        print(json.dumps(entry))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve /jav_config.ws over HTTPS using the local localhost certificate."
    )
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8443)
    parser.add_argument("--pfxfile", type=Path, default=DEFAULT_PFX)
    parser.add_argument("--pfxpassword", default="opennxt-dev")
    parser.add_argument("--target-base-url", default=DEFAULT_TARGET)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cert_path, key_path = export_pfx_to_temp_pem_files(args.pfxfile, args.pfxpassword)
    server = http.server.ThreadingHTTPServer((args.listen_host, args.listen_port), JavConfigProxyHandler)
    server.proxy_config = ProxyConfig(target_base_url=args.target_base_url)  # type: ignore[attr-defined]

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)

    print(
        json.dumps(
            {
                "listen": f"https://{args.listen_host}:{args.listen_port}/jav_config.ws",
                "target": args.target_base_url,
                "cert": cert_path,
                "key": key_path,
            }
        )
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
