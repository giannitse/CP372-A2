"""
CP372 - Assignment 2: Stop-and-Wait Sender
"""

import socket
import struct
import os
import time
import random
import sys

# ─── Configuration ────────────────────────────────────────────────────────────
RECEIVER_IP   = "127.0.0.1"
RECEIVER_PORT = 9000
SENDER_PORT   = 9001
BUFFER_SIZE   = 4096
PAYLOAD_SIZE  = 1024
TIMEOUT       = 1.0
MAX_RETRIES   = 20

# ─── Packet Types ─────────────────────────────────────────────────────────────
TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2   # notify receiver a file transfer is starting
TYPE_END   = 3   # notify receiver file transfer is complete

# ─── Packet Format ────────────────────────────────────────────────────────────
HEADER_FMT  = "!IIBh"      # network byte order: uint32, uint32, uint8, int16
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 11 bytes


def build_packet(seq: int, ack: int, pkt_type: int, payload: bytes = b"") -> bytes:
    """Serialize a packet to bytes."""
    header = struct.pack(HEADER_FMT, seq, ack, pkt_type, len(payload))
    return header + payload


def parse_packet(data: bytes):
    """Deserialize bytes into (seq, ack, pkt_type, payload)."""
    if len(data) < HEADER_SIZE:
        raise ValueError("Packet too short")
    seq, ack, pkt_type, payload_len = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE: HEADER_SIZE + payload_len]
    return seq, ack, pkt_type, payload


def send_with_ack(sock: socket.socket,
                  packet: bytes,
                  expected_ack_seq: int,
                  dest: tuple) -> int:
    """
    Send a packet and wait for the expected ACK using Stop-and-Wait.

    Returns the number of transmissions used (1 = no retransmit needed).
    Raises RuntimeError if MAX_RETRIES exceeded.
    """
    attempts = 0
    transmissions = 0

    while attempts < MAX_RETRIES:
        sock.sendto(packet, dest)
        transmissions += 1
        attempts += 1

        sock.settimeout(TIMEOUT)
        try:
            raw, _ = sock.recvfrom(BUFFER_SIZE)
            seq, ack, pkt_type, _ = parse_packet(raw)
            if pkt_type == TYPE_ACK and ack == expected_ack_seq:
                return transmissions          # ACK received — move on
            # Wrong ACK (duplicate or out-of-order) — retransmit
            print(f"  [!] Wrong ACK {ack}, expected {expected_ack_seq}. Retransmitting…")
        except socket.timeout:
            print(f"  [!] Timeout on seq={expected_ack_seq}, attempt {attempts}. Retransmitting…")

    raise RuntimeError(f"Exceeded MAX_RETRIES ({MAX_RETRIES}) waiting for ACK {expected_ack_seq}")


def transfer_file(filepath: str):
    """Transfer a file to the receiver using Stop-and-Wait."""
    if not os.path.isfile(filepath):
        print(f"Error: '{filepath}' not found.")
        sys.exit(1)

    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)
    print(f"[Sender] Transferring '{filename}' ({filesize} bytes) to {RECEIVER_IP}:{RECEIVER_PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", SENDER_PORT))
    dest = (RECEIVER_IP, RECEIVER_PORT)

    total_retransmits = 0
    seq = 0
    start_time = time.time()

    # ── Step 1: Send START notification ───────────────────────────────────────
    print("[Sender] Sending START packet…")
    meta = f"{filename}:{filesize}".encode()
    start_pkt = build_packet(seq, 0, TYPE_START, meta)
    txs = send_with_ack(sock, start_pkt, seq, dest)
    total_retransmits += txs - 1
    print(f"[Sender] START acknowledged (seq={seq})")
    seq += 1

    # ── Step 2: Send file chunks ───────────────────────────────────────────────
    with open(filepath, "rb") as f:
        chunk_index = 0
        while True:
            chunk = f.read(PAYLOAD_SIZE)
            if not chunk:
                break

            pkt = build_packet(seq, 0, TYPE_DATA, chunk)
            txs = send_with_ack(sock, pkt, seq, dest)
            total_retransmits += txs - 1

            chunk_index += 1
            if chunk_index % 50 == 0 or len(chunk) < PAYLOAD_SIZE:
                elapsed = time.time() - start_time
                sent_bytes = chunk_index * PAYLOAD_SIZE
                throughput = sent_bytes / elapsed if elapsed > 0 else 0
                print(f"  [Progress] chunk={chunk_index}, seq={seq}, "
                      f"elapsed={elapsed:.2f}s, throughput={throughput/1024:.1f} KB/s")

            seq += 1

    # ── Step 3: Send END notification ─────────────────────────────────────────
    print("[Sender] Sending END packet…")
    end_pkt = build_packet(seq, 0, TYPE_END)
    txs = send_with_ack(sock, end_pkt, seq, dest)
    total_retransmits += txs - 1
    print(f"[Sender] END acknowledged (seq={seq})")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    throughput = filesize / elapsed if elapsed > 0 else 0
    print("\n[Sender] Transfer complete!")
    print(f"  File size       : {filesize} bytes")
    print(f"  Total time      : {elapsed:.4f} s")
    print(f"  Throughput      : {throughput/1024:.2f} KB/s")
    print(f"  Retransmissions : {total_retransmits}")

    sock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: create a small test file and send it
        test_file = "test_input.txt"
        if not os.path.exists(test_file):
            with open(test_file, "wb") as f:
                f.write(b"A" * 10_240)    # 10 KB of 'A'
            print(f"[Sender] Created test file '{test_file}' (10 KB)")
        filepath = test_file
    else:
        filepath = sys.argv[1]

    transfer_file(filepath)