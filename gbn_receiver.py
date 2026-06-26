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
LOSS_RATE     = 0.05 #0 = No packet loss, 1 = 100% packet loss
CORRUPTION_RATE = 0.1
LISTEN_TIMEOUT = 5

# ─── Packet Types ─────────────────────────────────────────────────────────────
TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2
TYPE_END   = 3

# ─── Packet Format ────────────────────────────────────────────────────────────
# Header: seq_num (4B) | ack_num (4B) | pkt_type (1B) | payload_len (2B)
HEADER_FMT  = "!iibHH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 11 bytes


#Calculates checksum to check network efficacy 
def calculate_checksum(seq, ack, ptype, payload: bytes):
# make temporary packet
    chkSum = 0
    
    tempPack = struct.pack(HEADER_FMT, seq, ack, ptype, len(payload), 0) + payload
    
    # Increment through packet data
    for i in range(0, len(tempPack), 2):
        #check if this is the last two byte section
        if len(tempPack) > i+1:
        #if it isnt then continue adding two bytes at a time to the checksum value
            chkSum += int.from_bytes(tempPack[i:i+2], byteorder='big')
        #if last byte
        else:
            #pad the end of the byte string with 0's, and add to the checksum value
            chkSum += int.from_bytes(tempPack[i:] + b'\x00', byteorder='big')
        
    # Check for overflow
    while (chkSum >> 16):
    # If overflow, 1's compliment wrap/carry over
        chkSum = (chkSum & 0xFFFF) + (chkSum >> 16)
    # invert the 1's and 0's and return
    return (~chkSum & 0xFFFF)

def validChkSum(chk1, chk2):
    
    return chk1 == chk2

def build_packet(seq: int, ack: int, pkt_type: int, payload: bytes = b"") -> bytes:
    """Serialize a packet to bytes."""
    
    chk = calculate_checksum(seq, ack, pkt_type, payload)
    
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

def simulate_corrupt() -> bool:

    return CORRUPTION_RATE > 0.0 and random.random() < LOSS_RATE

def active():
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    
    sock.bind((RECEIVER_IP, RECEIVER_PORT))
    
    while True:
        
        print("Waiting for transfer start packet...")
        
        expected_seq = None
        filename     = None
        filesize     = None
        outfile      = None
        bytes_received = 0
        packets_received = 0
        packets_dropped  = 0
        start_time   = None
        
        sock.setblocking(True)
            
        while True:
        
            data, sender_addr = sock.recvfrom(BUFFER_SIZE)
            
            if simulate_loss():
                
                packets_dropped += 1
                print("Simulated packet loss occurred, ignoring this packet's arrival")
                continue
            
            if simulate_corrupt():
                
                print("Corrupted packet checksum")
                
                packArray = bytearray(data)
                
                packArray[-2] = 0x00
                
                data = bytes(packArray)
            
            try:
                
                seq, ack, pktType, payload, checksum = parse_packet(data)
                
            except ValueError:
                
                print(f"ValueError, malformed packet from sender {sender_addr}, dropping.")
                # set packet type to a number that wont allow this packet to be processed, skipping all if statements and looping back around to pick up another packet
                pktType = -1
                
                
            newCheck = calculate_checksum(seq, ack, pktType, payload)
            
            if not validChkSum(checksum, newCheck):     
                  
                  print(f"Checksum not valid, data possibly lost in transfer for packet: {seq}")
                  
                  packets_dropped += 1
                
            if pktType == TYPE_START:
                    
                # Parse metadata: "filename:filesize"
                try:
                    meta = payload.decode()
                    filename, filesize_str = meta.split(":", 1)
                    filesize = int(filesize_str)
                except Exception:
                    filename = f"transfer_{int(time.time())}.bin"
                    filesize = -1   # unknown
                    
                expected_seq = seq
                    
                start_time = time.time()
                    
                print(f"[Receiver] START received from {sender_addr}")
                print(f"           filename={filename}, expected_size={filesize} bytes, seq={seq}")

                # Open output file
                outpath = os.path.join(OUTPUT_DIR, filename)
                outfile = open(outpath, "wb")

                # ACK the START
                send_ack(sock, expected_seq, sender_addr)
                print(f"  [ACK] Sent ACK for START seq={expected_seq}")
                    
                start_time = time.time()
                    
                expected_seq += 1
                break
                    
            else:
                    
                print("Incorrect packet received, n")
                    
        fin_transfer = False
        
        packets_to_process = []
        
        sock.setblocking(False)
        
        while not fin_transfer:
            
            highest_seq = seq
            
            packets_to_process = []
            
            while True:
                
                try:
                
                    packets_to_process.append(sock.recvfrom(BUFFER_SIZE))
                    
                except BlockingIOError:
                    
                    break
                
                except ConnectionResetError:
                    
                    print("Connection Closed")
                    
                    fin_transfer = True
                    
                    break
            
            validSeq = False
            
            if not packets_to_process:
                
                time.sleep(0.001)
                
                continue
            
            for pack in packets_to_process:
                
                if simulate_loss():
                
                    packets_dropped += 1
                    
                    print("Simulated packet loss occurred, ignoring this packet's arrival")
                    
                    continue
                
                if simulate_corrupt():
                    
                    print("Corrupted packet checksum")
                    
                    packArray = bytearray(pack[0])
                    
                    packArray[-2] = 0x00
                    
                    pack = (bytes(packArray), pack[1])
            
                try:
                            
                    seq, ack, pktType, payload, checksum = parse_packet(pack[0])
                        
                    newCheck = calculate_checksum(seq, ack, pktType, payload)
                        
                except ValueError:
                        
                    print(f"ValueError, malformed packet from sender {sender_addr}, dropping.")
                    # set packet type to a number that wont allow this packet to be processed, skipping all if statements and looping back around to pick up another packet
                    continue
                        
                        
                if not validChkSum(checksum, newCheck):
                    
                    print(f"Checksum not valid, data possibly lost in transfer for packet: {seq}, dropping")
                    
                    packets_dropped += 1
                    
                    continue
                        
                if seq == expected_seq:
                            
                    if pktType == TYPE_DATA:
                        
                        outfile.write(payload)
                        
                        expected_seq += 1
                        
                    elif pktType == TYPE_END:
                        
                        fin_transfer = True
                        
                        print(f"Transfer Finished, END packet received")
                        
                        break
                            
                    packets_received += 1
                            
                    bytes_received += len(payload)
                        
                    highest_seq = seq
                    
                    validSeq = True
                    
                else:
                    
                    validSeq = False
                    
                    break
                                
            if not validSeq:
                            
                highest_seq = expected_seq - 1
                
            if packets_to_process and not fin_transfer:
                    
                send_ack(sock, highest_seq, sender_addr)
                
            if time.time() - start_time > LISTEN_TIMEOUT:
                
                print("Connection timeout, no activity from sender, going back to listening for start")
                
                break
            
        if outfile:
            duration = time.time() - start_time
            throughput = bytes_received/duration
            outfile.close()
            print(f"Finished transfer, Summary:\nDuration: {duration:.4f} Seconds\nFile Size: {filesize} Bytes\nAverage Throughput: {throughput/1024:.2f} KB/s\nLost Packets: {packets_dropped}")
            
                        
if __name__ == "__main__":
    
    active()
                    
                    
                    