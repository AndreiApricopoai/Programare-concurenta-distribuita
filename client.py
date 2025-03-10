import argparse
import socket
import ssl
import time
import asyncio
from aioquic.asyncio.client import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

# TCP
def tcp_client(host, port, data_size, buffer_size):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host, port))

    data = b'X' * buffer_size
    total_bytes_sent = 0
    total_messages = 0
    start_time = time.time()

    while total_bytes_sent < data_size:
        client_socket.sendall(data)
        total_bytes_sent += len(data)
        total_messages += 1

    client_socket.close()
    end_time = time.time()
    print(f"Protocol: TCP\nTotal Messages Sent: {total_messages}\nTotal Bytes Sent: {total_bytes_sent}\nTime: {end_time - start_time} sec")

# UDP
def udp_client(host, port, data_size, buffer_size, stop_wait):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    data = b'X' * buffer_size
    total_bytes_sent = 0
    total_messages = 0
    start_time = time.time()

    while total_bytes_sent < data_size:
        client_socket.sendto(data, (host, port))
        total_bytes_sent += len(data)
        total_messages += 1

        if stop_wait:
            client_socket.recvfrom(1024)  # Wait for ACK

    client_socket.sendto(b'END', (host, port))
    end_time = time.time()
    print(f"Protocol: UDP\nTotal Messages Sent: {total_messages}\nTotal Bytes Sent: {total_bytes_sent}\nTime: {end_time - start_time} sec")

# QUIC
class FixedQuicClientProtocol(QuicConnectionProtocol):
    def __init__(self, connection, stream_handler, data_size, buffer_size, stop_wait):
        super().__init__(connection)
        self.data_size = data_size
        self.buffer_size = buffer_size
        self.stop_wait = stop_wait
        self.total_bytes_sent = 0
        self.total_messages = 0
        self.start_time = time.time()
        self._ack_waiter = asyncio.get_event_loop().create_future()

    async def send_data(self):
        stream_id = self._quic.get_next_available_stream_id()
        data = b'X' * self.buffer_size

        while self.total_bytes_sent < self.data_size:
            self._quic.send_stream_data(stream_id, data)
            self.total_bytes_sent += len(data)
            self.total_messages += 1

            if self.stop_wait:
                await self._ack_waiter
                self._ack_waiter = asyncio.get_event_loop().create_future()

            self.transmit()

        self._quic.send_stream_data(stream_id, b'END', end_stream=True)
        self.transmit()
        end_time = time.time()
        print(f"Protocol: QUIC\nTotal Messages Sent: {self.total_messages}\nTotal Bytes Sent: {self.total_bytes_sent}\nTime: {end_time - self.start_time} sec")

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived) and self.stop_wait:
            self._ack_waiter.set_result(None)

async def quic_client(host, port, data_size, buffer_size, stop_wait):
    configuration = QuicConfiguration(is_client=True, alpn_protocols=["hq-interop"])
    configuration.verify_mode = ssl.CERT_NONE  

    async with connect(
        host, port, configuration=configuration, create_protocol=lambda connection, stream_handler: FixedQuicClientProtocol(
            connection, stream_handler, data_size, buffer_size, stop_wait
        )
    ) as client:
        await client.send_data()

# Argument Parsing
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=str, required=True, choices=['tcp', 'udp', 'quic'], help="Protocol to use (TCP, UDP, QUIC)")
    parser.add_argument("--host", type=str, required=True, help="Server address")
    parser.add_argument("--port", type=int, required=True, help="Server port")
    parser.add_argument("--size", type=int, required=True, help="Data size to transfer")
    parser.add_argument("--buffer", type=int, required=True, help="Buffer size for sending data")
    parser.add_argument("--stop_wait", action='store_true', help="Enable Stop-and-Wait Acknowledgment for UDP/QUIC")
    args = parser.parse_args()

    if args.protocol == 'tcp':
        tcp_client(args.host, args.port, args.size, args.buffer)
    elif args.protocol == 'udp':
        udp_client(args.host, args.port, args.size, args.buffer, args.stop_wait)
    elif args.protocol == 'quic':
        asyncio.run(quic_client(args.host, args.port, args.size, args.buffer, args.stop_wait))
