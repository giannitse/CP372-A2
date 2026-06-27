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
TIMEOUT = 0.25
MAX_RETRANSMITS = 30

TYPE_DATA  = 0
TYPE_ACK   = 1
TYPE_START = 2   # notify receiver a file transfer is starting
TYPE_END   = 3   # notify receiver file transfer is complete

HEADER_FMT  = "!iibHH"      # network byte order: uint32, uint32, uint8, int16, uint16
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

# builds a packet with sequence number, ack, type, size of data, and also calculates and packs a checksum value using the above function
def build_packet(seq: int, ack: int, pkt_type: int, payload: bytes = b"") -> bytes:
    
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
# main transfer function, 90% of this probably should be abstracted, but not enough time... 
def transfer_file(filepath: str):
    #checks if file to be transferred exists
    if not os.path.isfile(filepath):
        
        print(f"Error: '{filepath}' not found.") 
        sys.exit(1)
    #   extracts name and size of file to variables for faster and cleaner access 
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)
    # status message
    print(f"[Sender] Transferring '{filename}' ({filesize} bytes) to {REC_IP}:{REC_PORT}")
    # create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # bind socket to local
    sock.bind(("", SEND_PORT))
    # variables to track status of transfer
    pack_dest = (REC_IP, REC_PORT)
    seq = 0
    base = 0
    packets_lost = 0
    packs_in_transit = []
    packs_to_send = []
    retries = 0
    #Send start packet
    print("Sending start packet...")
    
    file_info = f"{filename}:{filesize}".encode("utf-8")
    # build start packet
    start_packet = build_packet(seq, 0, TYPE_START, file_info)
    # send start packet to notify receiver of file transfer
    send_packets(sock, [start_packet], pack_dest)
    
    # mark timestamp at start of sending
    start_time = time.time()
    #set timeout clock to time of packet transfer
    timeoutClock = time.time()
    
    # increase current seq
    seq += 1
    # update the list that tracks unacknowledged packs
    packs_in_transit.append(start_packet)
    #   open file for reading raw bytes
    f = open(filepath, 'rb')
    #calculate the total packets for the receiver to receive, using ceiling function, and accounting for start packet
    total_packs = (-(os.path.getsize(filepath)// -PAYLOAD_SIZE)) + 1
    
    transmission_fin = False
    
    retries = 0
#
    while base < total_packs and retries < MAX_RETRANSMITS:
        
        availableaWndwSize = WINDOW_SIZE - (len(packs_to_send) + len(packs_in_transit))
        
        if availableaWndwSize > 0 and not transmission_fin:
            
            for i in range(availableaWndwSize):
                
                chunk = f.read(PAYLOAD_SIZE)
                
                if not chunk:
                    transmission_fin = True
                    break
                
                packs_to_send.append(build_packet(seq, 0, TYPE_DATA, chunk))
                
                seq += 1

# check if there are packets to send
        if packs_to_send:
            
            send_packets(sock, packs_to_send, pack_dest)
            
            print(f"Sent packets from {base}:{seq - 1}")
        
            packs_in_transit.extend(packs_to_send)
        
            packs_to_send = []
        
        sock.setblocking(False)
        
        highest_ack = base - 1
        
        acked = False
        
# Receive all acks currently in buffer, find the highest ack and use that as the basis for sliding the window up
        while True:
            
            try:
                # receive the ack value from the selected packet
                ack = parse_packet(sock.recvfrom(BUFFER_SIZE)[0])[1]
                # compare against base (first iteration) / highest received ack so far
                if ack > highest_ack and ack >= base:
                    
                    highest_ack = ack
                    
                    acked = True
                    
                    print(f"Received Ack: {ack}")

                    
            # End loop when buffer is empty
            except BlockingIOError:
                
                break
            # Just incase anything else happens we break the loop and ignore the acks, allowing resending of data packets from the current window base
            except Exception as e:
                
                print(f"Error '{e}' occurred, if this continues, close program and ensure receiver is operating")
                
                break
            
# Check if the highest ack was updated (if an ack was received that acknowledges an in-transit-packet) in this cycle    
        if acked:
            # how much to slide the window by
            inc = highest_ack - base + 1
            # checking if inc progresses window or not
            if inc > 0:
                
                print(f"Adjusting window forward by {inc}")
                # adjust base using same above formula, just reorganized
                base = highest_ack + 1
                # remove acknowledged packet from the in transit window
                packs_in_transit = packs_in_transit[inc:]
            
            timeoutClock = time.time()
            
            retries = 0
            
        
            
# Manually check for timeout
# we have to manually check because we set blocking to false so we can process multiple ack messages in one cycle
        if base < total_packs and (time.time() - timeoutClock) > TIMEOUT:
            
            print(f"Connection timeout, ensure receiver is operational. Packets lost, retransmitting window")
            # place the in-transit packets back into the sending list
            packs_to_send.extend(packs_in_transit)
            # keep track of how many packets are retransmitted / not received
            packets_lost += len(packs_in_transit)
            # remove the packets from the in-transit list
            packs_in_transit = []
            
            retries += 1
            
            print(f"Retransmit: {retries} / {MAX_RETRANSMITS}")
            
        time.sleep(0.001)    
        
        
        
        
    if retries >= MAX_RETRANSMITS:
            
        print(f"Unable to establish stable transfer state with receiver, closing sender")
            
    else:
         
        print("Sending END packet...")
        
        send_packets(sock, [build_packet(seq, 0, TYPE_END)], pack_dest)
        
        timeoutClock = time.time()
                    
        throughputAvg = os.path.getsize(filepath) / (time.time() - start_time)
            
        print(f"Finished transfer, Summary:\nDuration: {time.time() - start_time:.4f} Seconds\nFile Size: {os.path.getsize(filepath)} Bytes\nAverage Throughput: {throughputAvg/1024:.2f} KB/s\nLost Packets: {packets_lost}")
    
    
    f.close()
    
    sock.close()
    
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

    transfer_file("pic\WIN_20260403_23_57_52_Pro.jpg")