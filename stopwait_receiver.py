"""
CP372 - Assignment 2: Stop-and-Wait Receiver
"""

import socket
import struct
import os
import time
import random
import sys

# ─── Configuration ────────────────────────────────────────────────────────────
RECEIVER_IP   = "0.0.0.0"
RECEIVER_PORT = 9000
BUFFER_SIZE   = 4096
OUTPUT_DIR    = "received_files"    # directory where received files are saved
LOSS_RATE     = 0.0                 # set to e.g. 0.1 for 10% simulated packet loss

# ─── Packet Types ─────────────────────────────────────────────────────────────
TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2
TYPE_END   = 3

# ─── Packet Format ────────────────────────────────────────────────────────────
# Header: seq_num (4B) | ack_num (4B) | pkt_type (1B) | payload_len (2B)
HEADER_FMT  = "!IIBh"
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


def send_ack(sock: socket.socket, ack_seq: int, dest: tuple):
    """Send a cumulative ACK for ack_seq."""
    ack_pkt = build_packet(0, ack_seq, TYPE_ACK)
    sock.sendto(ack_pkt, dest)


def simulate_loss() -> bool:
    """Return True if the packet should be dropped (simulated loss)."""
    return LOSS_RATE > 0.0 and random.random() < LOSS_RATE


def receive_file():
    """
    Main receiver loop.

    State machine per transfer:
        IDLE      – waiting for a TYPE_START packet
        RECEIVING – accumulating TYPE_DATA packets in order
        DONE      – TYPE_END received; file written and closed
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((RECEIVER_IP, RECEIVER_PORT))
    print(f"[Receiver] Listening on {RECEIVER_IP}:{RECEIVER_PORT}  "
          f"(loss_rate={LOSS_RATE*100:.0f}%)")

    while True:   # outer loop: accept multiple sequential transfers
        print("\n[Receiver] Waiting for new transfer…")

        # ── State: IDLE ───────────────────────────────────────────────────────
        # Wait for a TYPE_START packet; ignore (and ACK-resend) anything else
        expected_seq = None
        filename     = None
        filesize     = None
        outfile      = None
        bytes_received = 0
        packets_received = 0
        packets_dropped  = 0
        start_time   = None

        while True:
            raw, sender_addr = sock.recvfrom(BUFFER_SIZE)

            # Simulated packet loss
            if simulate_loss():
                packets_dropped += 1
                print(f"  [LOSS] Dropped incoming packet (simulated)")
                continue

            try:
                seq, ack, pkt_type, payload = parse_packet(raw)
            except ValueError as e:
                print(f"  [!] Malformed packet from {sender_addr}: {e}")
                continue

            if pkt_type == TYPE_START:
                # Parse metadata: "filename:filesize"
                try:
                    meta = payload.decode()
                    filename, filesize_str = meta.split(":", 1)
                    filesize = int(filesize_str)
                except Exception:
                    filename = f"transfer_{int(time.time())}.bin"
                    filesize = -1   # unknown

                expected_seq = seq      # seq of the START packet
                start_time   = time.time()

                print(f"[Receiver] START received from {sender_addr}")
                print(f"           filename={filename}, expected_size={filesize} bytes, seq={seq}")

                # Open output file
                outpath = os.path.join(OUTPUT_DIR, filename)
                outfile = open(outpath, "wb")

                # ACK the START
                send_ack(sock, expected_seq, sender_addr)
                print(f"  [ACK] Sent ACK for START seq={expected_seq}")

                expected_seq += 1   # next expected is the first DATA packet
                break               # move to RECEIVING state

            else:
                # Received something before START — ignore silently
                print(f"  [?] Unexpected pkt_type={pkt_type} before START; ignoring.")
                continue

        # ── State: RECEIVING ─────────────────────────────────────────────────
        transfer_complete = False
        while not transfer_complete:
            raw, sender_addr = sock.recvfrom(BUFFER_SIZE)

            # Simulated packet loss
            if simulate_loss():
                packets_dropped += 1
                print(f"  [LOSS] Dropped packet (simulated), expected seq={expected_seq}")
                # Do NOT send an ACK — the sender's timer will fire and retransmit
                continue

            try:
                seq, ack, pkt_type, payload = parse_packet(raw)
            except ValueError as e:
                print(f"  [!] Malformed packet: {e}")
                continue

            # ── TYPE_DATA ─────────────────────────────────────────────────────
            if pkt_type == TYPE_DATA:
                if seq == expected_seq:
                    # In-order packet: accept it
                    outfile.write(payload)
                    bytes_received += len(payload)
                    packets_received += 1

                    send_ack(sock, seq, sender_addr)

                    if packets_received % 50 == 0:
                        elapsed = time.time() - start_time
                        tp = bytes_received / elapsed if elapsed > 0 else 0
                        print(f"  [Progress] seq={seq}, bytes={bytes_received}, "
                              f"elapsed={elapsed:.2f}s, ~{tp/1024:.1f} KB/s")

                    expected_seq += 1

                elif seq < expected_seq:
                    # Duplicate packet (sender retransmitted because our ACK was lost)
                    print(f"  [DUP] Duplicate seq={seq}, expected={expected_seq}. Re-ACKing.")
                    send_ack(sock, seq, sender_addr)

                else:
                    # Out-of-order packet (shouldn't happen in Stop-and-Wait, but guard anyway)
                    print(f"  [OOO] Out-of-order seq={seq}, expected={expected_seq}. Discarding.")
                    # Send ACK for the last successfully received packet
                    if expected_seq > 0:
                        send_ack(sock, expected_seq - 1, sender_addr)

            # ── TYPE_END ──────────────────────────────────────────────────────
            elif pkt_type == TYPE_END:
                if seq == expected_seq:
                    print(f"[Receiver] END received (seq={seq}). Transfer complete.")
                    send_ack(sock, seq, sender_addr)
                    transfer_complete = True
                elif seq < expected_seq:
                    # Duplicate END
                    print(f"  [DUP] Duplicate END seq={seq}. Re-ACKing.")
                    send_ack(sock, seq, sender_addr)
                else:
                    print(f"  [OOO] Out-of-order END seq={seq}, expected={expected_seq}. Discarding.")

            # ── TYPE_START (retransmitted START) ──────────────────────────────
            elif pkt_type == TYPE_START:
                # Our START ACK was lost; re-send it
                print(f"  [DUP] Duplicate START seq={seq}. Re-ACKing.")
                send_ack(sock, seq, sender_addr)

            else:
                print(f"  [?] Unknown pkt_type={pkt_type}. Ignoring.")

        # ── Finalise file ─────────────────────────────────────────────────────
        outfile.close()
        elapsed = time.time() - start_time
        throughput = bytes_received / elapsed if elapsed > 0 else 0

        print(f"\n[Receiver] File saved → {os.path.join(OUTPUT_DIR, filename)}")
        print(f"  Bytes written   : {bytes_received}")
        print(f"  Packets received: {packets_received}")
        print(f"  Packets dropped : {packets_dropped}  (simulated loss)")
        print(f"  Total time      : {elapsed:.4f} s")
        print(f"  Throughput      : {throughput/1024:.2f} KB/s")


if __name__ == "__main__":
    # Optionally accept a loss rate from the command line: python3 receiver_stopwait.py 0.1
    if len(sys.argv) >= 2:
        LOSS_RATE = float(sys.argv[1])
        print(f"[Receiver] Loss rate set to {LOSS_RATE*100:.0f}%")

    try:
        receive_file()
    except KeyboardInterrupt:
        print("\n[Receiver] Shutting down.")