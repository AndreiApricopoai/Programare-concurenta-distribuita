import argparse
import socket
import asyncio
from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived, ConnectionTerminated

# TCP
def tcp_server(host, port, buffer_size):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    print(f"TCP Server started on {host}:{port}")

    while True:
        conn, addr = server_socket.accept()
        print(f"Connected by {addr}")

        total_bytes_received = 0
        total_messages = 0

        while True:
            data = conn.recv(buffer_size)
            if not data:
                break
            total_bytes_received += len(data)
            total_messages += 1

        conn.close()
        print(f"Protocol: TCP\nTotal Messages Received: {total_messages}\nTotal Bytes Received: {total_bytes_received}")

# UDP
def udp_server(host, port, buffer_size, stop_wait):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((host, port))
    print(f"UDP Server started on {host}:{port}")

    total_bytes_received = 0
    total_messages = 0

    while True:
        data, addr = server_socket.recvfrom(buffer_size)
        if data == b'END':
            break

        total_bytes_received += len(data)
        total_messages += 1

        if stop_wait:
            server_socket.sendto(b'ACK', addr)

    print(f"Protocol: UDP\nTotal Messages Received: {total_messages}\nTotal Bytes Received: {total_bytes_received}")

# QUIC
class FixedQuicServerProtocol(QuicConnectionProtocol):
    def __init__(self, connection, stream_handler, buffer_size, stop_wait):
        super().__init__(connection)
        self.buffer_size = buffer_size
        self.stop_wait = stop_wait
        self.total_bytes_received = 0
        self.total_messages = 0

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            if event.data == b'END':
                print(f"Protocol: QUIC\nTotal Messages Received: {self.total_messages}\nTotal Bytes Received: {self.total_bytes_received}")
                return

            self.total_bytes_received += len(event.data)
            self.total_messages += 1

            if self.stop_wait:
                self._quic.send_stream_data(event.stream_id, b'ACK')
                self.transmit()

async def quic_server(host, port, buffer_size, stop_wait):
    configuration = QuicConfiguration(is_client=False)
    configuration.load_cert_chain("cert.pem", "key.pem")
    configuration.alpn_protocols = ["hq-interop"]

    print(f"QUIC Server started on {host}:{port}")

    def create_server_protocol(connection, stream_handler):
        return FixedQuicServerProtocol(
            connection, stream_handler, buffer_size=buffer_size, stop_wait=stop_wait
        )

    await serve(
        host=host,
        port=port,
        configuration=configuration,
        create_protocol=create_server_protocol,
    )

    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        print("\nQUIC Server shutting down...")



# Argument Parsing
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=str, required=True, choices=['tcp', 'udp', 'quic'], help="Protocol to use (TCP, UDP, QUIC)")
    parser.add_argument("--host", type=str, required=True, help="Server address")
    parser.add_argument("--port", type=int, required=True, help="Server port")
    parser.add_argument("--buffer", type=int, required=True, help="Buffer size for receiving data")
    parser.add_argument("--stop_wait", action='store_true', help="Enable Stop-and-Wait Acknowledgment for UDP/QUIC")
    args = parser.parse_args()

    if args.protocol == 'tcp':
        tcp_server(args.host, args.port, args.buffer)
    elif args.protocol == 'udp':
        udp_server(args.host, args.port, args.buffer, args.stop_wait)
    elif args.protocol == 'quic':
        asyncio.run(quic_server(args.host, args.port, args.buffer, args.stop_wait))
