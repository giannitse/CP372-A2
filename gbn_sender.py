#CP372 Go Back N sender

import socket
import struct
import os
import time
import random
import sys

# Go-Back-N Sender

REC_IP = "127.0.0.1"
REC_PORT = 9000
SEND_PORT = 9001
PAYLOAD_SIZE = 1024
BUFFER_SIZE = 4096
WINDOW_SIZE = 4
TIMEOUT = 1

TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2   # notify receiver a file transfer is starting
TYPE_END   = 3   # notify receiver file transfer is complete

HEADER_FMT  = "!iibhh"      # network byte order: uint32, uint32, uint8, int16, uint16
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

def transfer_file(filepath: str):
    
    if not os.path.isfile(filepath):
        
        print(f"Error: '{filepath}' not found.") 
        sys.exit(1)
        
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)
    
    print(f"[Sender] Transferring '{filename}' ({filesize} bytes) to {REC_IP}:{REC_PORT}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    sock.bind(("", SEND_PORT))
    
    start_time = time.time()
    
    pack_dest = (REC_IP, REC_PORT)
    
    seq = 0
    
    base = 0
    
    packets_lost = 0
    
    packs_in_transit = []
    
    packs_to_send = []

    #Send start packet
    print("Sending start packet...")
    
    file_info = f"{filename}:{filesize}".encode("utf-8")
    
    start_packet = build_packet(seq, 0, TYPE_START, file_info)
    
    send_packets(sock, [start_packet], pack_dest)
    
    timeoutClock = time.time()
    
    seq += 1
    
    packs_in_transit.append(start_packet)
    
    f = open(filepath, 'rb')
    #calculate the total packets for the receiver to receive, using ceiling function, and accounting for start packet
    total_packs = (-(os.path.getsize(filepath)// -PAYLOAD_SIZE)) + 1
    #temporarily set chunk to True to enter the while loop
#
    while base < total_packs:
        
        availableaWndwSize = WINDOW_SIZE - (len(packs_to_send) + len(packs_in_transit))
        
        if availableaWndwSize >= 0:
            
            for i in range(availableaWndwSize):
                
                chunk = f.read(PAYLOAD_SIZE)
                
                if not chunk:
                    
                    break
                
                packs_to_send.append(build_packet(seq, 0, TYPE_DATA, chunk))
                
                seq += 1

                
        send_packets(sock, packs_to_send, pack_dest)
        
        packs_in_transit.extend(packs_to_send)
        
        packs_to_send = []
        
        sock.setblocking(False)
        
        highest_ack = base
        
        acked = False
        
#        
        while True:
            
            try:
                
                ack = parse_packet(sock.recvfrom(BUFFER_SIZE)[0])[1]
                
                if ack > highest_ack:
                    
                    highest_ack = ack
                    
                    acked = True
                    
                    print(f"Received Ack: {ack}")
            
            except BlockingIOError:
                
                break
            
            except Exception as e:
                
                print(f"Error '{e}' occurred, if this continues, close program and ensure receiver is operating")
                
                break
            
#           
        if acked:
            
            inc = (highest_ack - base) + 1
            
            base = highest_ack + 1
            
            packs_in_transit = packs_in_transit[inc:]
            
            timeoutClock = time.time()
            
#
        if base < total_packs and (time.time() - timeoutClock) > TIMEOUT:
            
            seq = base
            
            print(f"Connection timeout, ensure receiver is operational. Packets lost, adjusting window")
            
            packs_to_send.extend(packs_in_transit)
            
            packets_lost += len(packs_in_transit)
            
            packs_in_transit = []
            
            
    print("Sending END packet...")
    
    send_packets(sock, [build_packet(seq, 0, TYPE_END)], pack_dest)
    
    f.close()
    
    sock.close()
    
    throughputAvg = os.path.getsize(filepath) / (time.time() - start_time)
    
    print(f"Finished transfer, Summary:\nDuration: {time.time() - start_time:.4f} Seconds\nFile Size: {os.path.getsize(filepath)} Bytes\nAverage Throughput: {throughputAvg/1024:.2f} KB/s\nLost Packets: {packets_lost}")
            
    return


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