# CP372 Go Back N receiver 

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
OUTPUT_DIR    = "received_files"
LOSS_RATE     = 0.0

# ─── Packet Types ─────────────────────────────────────────────────────────────
TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2
TYPE_END   = 3

# ─── Packet Format ────────────────────────────────────────────────────────────
# Header: seq_num (4B) | ack_num (4B) | pkt_type (1B) | payload_len (2B)
HEADER_FMT  = "!IIBh"
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 11 bytes


#Calculates checksum to check network efficacy 
def calculate_checksum(seq, ack, header_size, payload: bytes):
# Sum header fields
    chkSum = seq + ack + header_size + len(payload)
    # Increment through payload data
    for i in range(0, len(payload), 2):
        #check if this is the last two byte section
        if len(payload) > i+1:
        #if it isnt then continue adding two bytes at a time to the checksum value
            chkSum += int.from_bytes(payload[i:i+2], byteorder='big')
        #if last byte
        else:
            #pad the end of the byte string with 0's, and add to the checksum value
            chkSum += int.from_bytes(payload[i:] + b'\x00', byteorder='big')
        
    
    # Check for overflow
    while (chkSum >> 16):
    # If overflow, 1's compliment wrap/carry over
        chkSum = (chkSum & 0xFFFF) + (chkSum >> 16)
    # return without inverting
    return (~chkSum & 0xFFFF)

def dataLossChkSum(chk1, chk2):
    
    return chk1 == chk2

def build_packet(seq: int, ack: int, pkt_type: int, payload: bytes = b"") -> bytes:
    """Serialize a packet to bytes."""
    
    header = struct.pack(HEADER_FMT, seq, ack, pkt_type, len(payload), 0)
    
    chk = calculate_checksum(seq, ack, len(header), payload)
    
    header = struct.pack(HEADER_FMT, seq, ack, pkt_type, len(payload), chk)
    
    
    return header + payload


def parse_packet(data: bytes):
    """Deserialize bytes into (seq, ack, pkt_type, payload)."""
    if len(data) < HEADER_SIZE:
        raise ValueError("Packet too short")
    seq, ack, pkt_type, payload_len, chk = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE: HEADER_SIZE + payload_len]
    return seq, ack, pkt_type, payload, chk
# sends a window of packets
def send_packets(sock: socket.socket, packets: tuple, dest: tuple):
    
    for packet in packets:
        
        sock.sendto(packet, dest)
    
    return 

def send_ack(sock: socket.socket, ack_seq: int, dest: tuple):
    """Send a cumulative ACK for ack_seq."""
    ack_pkt = build_packet(0, ack_seq, TYPE_ACK)
    sock.sendto(ack_pkt, dest)
    
def simulate_loss() -> bool:
    """Return True if the packet should be dropped (simulated loss)."""
    return LOSS_RATE > 0.0 and random.random() < LOSS_RATE

def active():
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    
    sock.bind(RECEIVER_IP, RECEIVER_PORT)
    
    while True:
        
        expected_seq = None
        filename     = None
        filesize     = None
        outfile      = None
        bytes_received = 0
        packets_received = 0
        packets_dropped  = 0
        start_time   = None
            
        while True:
        
            data, sender = sock.recvfrom(BUFFER_SIZE)
            
            if simulate_loss():
                
                packets_dropped += 1
                print("Simulated packet loss occurred, ignoring this packet's arrival")
                continue