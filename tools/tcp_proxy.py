import argparse
import socket
import threading
import time


def log(message: str) -> None:
    print(message, flush=True)


def pipe(src: socket.socket, dst: socket.socket, label: str, counters: dict[str, int]) -> None:
    first_chunk = True
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            counters[label] = counters.get(label, 0) + len(data)
            if first_chunk:
                hex_preview = data[:32].hex(" ")
                log(f"{label} first-chunk bytes={len(data)} hex={hex_preview}")
                first_chunk = False
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client: socket.socket, remote_host: str, remote_port: int) -> None:
    started_at = time.time()
    client_addr = client.getpeername()
    upstream = socket.create_connection((remote_host, remote_port))
    upstream_addr = upstream.getpeername()
    counters: dict[str, int] = {"client->remote": 0, "remote->client": 0}
    log(f"accept client={client_addr} remote={upstream_addr}")
    t1 = threading.Thread(target=pipe, args=(client, upstream, "client->remote", counters), daemon=True)
    t2 = threading.Thread(target=pipe, args=(upstream, client, "remote->client", counters), daemon=True)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    client.close()
    upstream.close()
    duration = time.time() - started_at
    log(
        "close client={client} remote={remote} duration={duration:.3f}s bytes client->remote={c2r} remote->client={r2c}".format(
            client=client_addr,
            remote=upstream_addr,
            duration=duration,
            c2r=counters["client->remote"],
            r2c=counters["remote->client"],
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--remote-host", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    args = parser.parse_args()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.listen_host, args.listen_port))
    listener.listen()

    try:
        while True:
            client, _ = listener.accept()
            threading.Thread(
                target=handle,
                args=(client, args.remote_host, args.remote_port),
                daemon=True,
            ).start()
    finally:
        listener.close()


if __name__ == "__main__":
    main()
