import argparse
import atexit
import socket
import ssl
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


def preview_hex(data: bytes, limit: int = 64) -> str:
    return " ".join(f"{b:02x}" for b in data[:limit])


def looks_like_tls_client_hello(data: bytes) -> bool:
    if len(data) < 5:
        return False
    content_type = data[0]
    major = data[1]
    minor = data[2]
    return content_type == 0x16 and major == 0x03 and minor in (0x00, 0x01, 0x02, 0x03, 0x04)


def pump(src, dst, lines, prefix, byte_counter, first_chunks, lock):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            with lock:
                byte_counter[0] += len(data)
                first_chunks[0] += 1
                chunk_index = first_chunks[0]
                if chunk_index <= 5:
                    lines.append(
                        f"{prefix} first-chunk-{chunk_index} bytes={len(data)} hex={preview_hex(data)}"
                    )
                elif len(data) >= 1024:
                    lines.append(f"{prefix} chunk={len(data)}")
            dst.sendall(data)
    except OSError as exc:
        with lock:
            lines.append(f"{prefix} error={type(exc).__name__}: {exc}")
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def create_remote_stream(mode, args):
    if mode == "tls":
        remote_host = args.tls_remote_host or args.remote_host
        connect_host = args.tls_connect_host or remote_host
        remote_port = args.tls_remote_port or args.remote_port
        connect_port = args.tls_connect_port or remote_port
        raw_remote = socket.create_connection((connect_host, connect_port), timeout=args.connect_timeout)
        raw_remote.settimeout(args.socket_timeout)
        remote_context = ssl.create_default_context()
        remote_tls = remote_context.wrap_socket(raw_remote, server_hostname=remote_host)
        remote_tls.settimeout(args.socket_timeout)
        remote_target = f"{connect_host}:{connect_port}"
        if connect_host != remote_host or connect_port != remote_port:
            remote_target += f" (sni {remote_host}:{remote_port})"
        return remote_tls, remote_target

    remote_host = args.remote_host
    remote_port = args.remote_port
    raw_remote = socket.create_connection((remote_host, remote_port), timeout=args.connect_timeout)
    raw_remote.settimeout(args.socket_timeout)
    return raw_remote, f"{remote_host}:{remote_port}"


def handle_client(client_sock, session_id, args, output_dir: Path):
    lines = []
    lock = threading.Lock()
    started = datetime.now(timezone.utc).isoformat()
    lines.append(f"session#{session_id} start={started}")
    lines.append(f"session#{session_id} client={client_sock.getpeername()}")
    client_counter = [0]
    server_counter = [0]
    client_chunks = [0]
    server_chunks = [0]

    remote_stream = None

    try:
        client_sock.settimeout(args.socket_timeout)
        initial_peek = client_sock.recv(5, socket.MSG_PEEK)
        mode = "tls" if looks_like_tls_client_hello(initial_peek) else "raw"
        lines.append(f"session#{session_id} mode={mode} initial-peek={preview_hex(initial_peek)}")
        remote_stream, remote_target = create_remote_stream(mode, args)
        lines.append(f"session#{session_id} remote={remote_target}")

        client_stream = client_sock
        if mode == "tls":
            client_stream = args.ssl_context.wrap_socket(client_sock, server_side=True)
            client_stream.settimeout(args.socket_timeout)

        t1 = threading.Thread(
            target=pump,
            args=(client_stream, remote_stream, lines, f"{mode}-client->remote", client_counter, client_chunks, lock),
            daemon=True,
        )
        t2 = threading.Thread(
            target=pump,
            args=(remote_stream, client_stream, lines, f"remote->{mode}-client", server_counter, server_chunks, lock),
            daemon=True,
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except (ssl.SSLError, OSError) as exc:
        with lock:
            lines.append(f"session#{session_id} session-error={type(exc).__name__}: {exc}")
    finally:
        try:
            client_sock.close()
        except OSError:
            pass
        try:
            if remote_stream is not None:
                remote_stream.close()
        except OSError:
            pass

    lines.append(
        f"session#{session_id} bytes {mode}-client->remote={client_counter[0]} remote->{mode}-client={server_counter[0]}"
    )
    lines.append(f"session#{session_id} end={datetime.now(timezone.utc).isoformat()}")
    session_path = output_dir / f"session-{session_id:02d}-{args.timestamp}.log"
    session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=443)
    parser.add_argument("--remote-host", default="127.0.0.1")
    parser.add_argument("--remote-port", type=int, default=43595)
    parser.add_argument("--tls-remote-host", default=None)
    parser.add_argument("--tls-remote-port", type=int, default=0)
    parser.add_argument("--tls-connect-host", default=None)
    parser.add_argument("--tls-connect-port", type=int, default=0)
    parser.add_argument("--pfxfile", required=True)
    parser.add_argument("--pfxpassword", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-sessions", type=int, default=16)
    parser.add_argument("--accept-timeout", type=float, default=1.0)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--socket-timeout", type=float, default=5.0)
    parser.add_argument("--idle-timeout-seconds", type=int, default=1800)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    args.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    temp_dir = TemporaryDirectory(prefix="opennxt-lobby-tls-")
    atexit.register(temp_dir.cleanup)
    temp_path = Path(temp_dir.name)

    pfx_data = Path(args.pfxfile).read_bytes()
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        pfx_data,
        args.pfxpassword.encode("utf-8"),
    )
    if private_key is None or certificate is None:
        raise RuntimeError(f"Could not load certificate and private key from {args.pfxfile}")

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    if additional_certificates:
        cert_pem += b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in additional_certificates)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    cert_path = temp_path / "server-cert.pem"
    key_path = temp_path / "server-key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    try:
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1
    except AttributeError:
        pass
    try:
        ssl_context.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    args.ssl_context = ssl_context

    summary_lines = []
    session_id = 0
    last_accept = datetime.now(timezone.utc)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.listen_host, args.listen_port))
        listener.listen()
        listener.settimeout(args.accept_timeout)

        while session_id < args.max_sessions:
            if (datetime.now(timezone.utc) - last_accept).total_seconds() >= args.idle_timeout_seconds and session_id > 0:
                summary_lines.append(f"idle-timeout={args.idle_timeout_seconds}s")
                break

            try:
                client_sock, _ = listener.accept()
            except TimeoutError:
                continue

            last_accept = datetime.now(timezone.utc)
            session_id += 1
            session_lines = handle_client(client_sock, session_id, args, output_dir)
            summary_lines.extend(session_lines)
            summary_lines.append("")

    summary_path = output_dir / f"summary-{args.timestamp}.log"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
