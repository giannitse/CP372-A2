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
LOSS_RATE     = 0.05 # 0 = No packet loss, 1 = 100% packet loss
CORRUPTION_RATE = 0.05
LISTEN_TIMEOUT = 8

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
# determine whether or not to corrupt a packet
    return CORRUPTION_RATE > 0.0 and random.random() < LOSS_RATE

def active():
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # create socket and dir
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    # bind socket
    sock.bind((RECEIVER_IP, RECEIVER_PORT))
    # main listening loop
    while True:
        
        print("Waiting for transfer start packet...")
        # reset all local variables to defaults
        expected_seq = None
        filename     = None
        filesize     = None
        outfile      = None
        bytes_received = 0
        packets_received = 0
        packets_dropped  = 0
        start_time   = None
        # set blocking to true for each seperate file transfer, this will do nothing on first transfer, but during file transfer we set blocking to false, 
        # so for second transfer and beyond we need to reset
        sock.setblocking(True)
            # listen for start packet
        while True:
            # try to read a packet from buffer
            data, sender_addr = sock.recvfrom(BUFFER_SIZE)
            # simulate packet loss
            if simulate_loss():
                
                packets_dropped += 1
                print("Simulated packet loss occurred, ignoring this packet's arrival")
                continue
            # simulate corruption
            if simulate_corrupt():
                
                print("Corrupted packet checksum")
                
                packArray = bytearray(data)
                
                packArray[-2] = 0x00
                
                data = bytes(packArray)
            # unpack payload from start packet
            try:
                
                seq, ack, pktType, payload, checksum = parse_packet(data)
                
            except ValueError:
                
                print(f"ValueError, malformed packet from sender {sender_addr}, dropping.")
                # set packet type to a number that wont allow this packet to be processed, skipping all if statements and looping back around to pick up another packet
                pktType = -1
                
                # ensure proper transfer, no data modified or lost
            newCheck = calculate_checksum(seq, ack, pktType, payload)
            # if not valid data, skip this packet, this portion should be below the if pktType == TYPE_START if statement following best practice,
            # but too much work to change at this point, the placement has minimal to no effect on the program
            if not validChkSum(checksum, newCheck):     
                  
                print(f"Checksum not valid, data possibly lost in transfer for packet: {seq}")
                # incremennt dropped packet counter
                packets_dropped += 1
                
                continue
                # if start packet received
            if pktType == TYPE_START:
                    
                # Parse metadata: "filename:filesize"
                try:
                    meta = payload.decode()
                    filename, filesize_str = meta.split(":", 1)
                    filesize = int(filesize_str)
                except Exception:
                    filename = f"transfer_{int(time.time())}.bin"
                    filesize = -1   # unknown
                    # set transfer start time
                start_time = time.time()    
                # note the current time as of first packet, also oldest packet received
                timeoutTime = time.time()
                # set base expected seq
                expected_seq = seq
                    
                print(f"[Receiver] START received from {sender_addr}")
                print(f"           filename={filename}, expected_size={filesize} bytes, seq={seq}")

                # Open output file
                outpath = os.path.join(OUTPUT_DIR, filename)
                outfile = open(outpath, "wb")

                # ACK the START
                send_ack(sock, expected_seq, sender_addr)
                print(f"  [ACK] Sent ACK for START seq={expected_seq}")
                    # receiver now expects next packet sequence number
                expected_seq = seq + 1
                break
                    
            else:
                    
                print(f"Incorrect packet type received, expecting start packet")
            # keep track of whether file transfer finished
        fin_transfer = False
        # set blocking false so we can read multiple packets from buffer, the original program attempted to implement batch processing of packets received,
        # this was done to minimize amount of ack messages sent, however it proved challenging, buggy, and slow to implement. (at least how I did it, may try again after submission)
        # At least I now understand why Go Back N receivers have window size of 1...
        sock.setblocking(False)
# begin receiving data packets
        while not fin_transfer:
            # tracker to check whether a packet was received in this cycle or not
            packedProcessing = True
            # set the highest ack to the seq num of the last successfully received packet
            highest_seq = expected_seq - 1
        # buffer reading loop
            while True:
                
                try:
                # read packet from buffer
                    pack_data, sender_addr = sock.recvfrom(BUFFER_SIZE)
                    # update receival time
                    timeoutTime = time.time()
                # if buffer empty, set packet processing tracker to false
                except BlockingIOError:
                    
                    packedProcessing = False
                    
                    break
                # if something happens to socket or network
                except ConnectionResetError:
                    
                    print("Connection Closed")
                    
                    fin_transfer = True
                    
                    break
            
                # already commented on these 
                if simulate_loss():       
                    packets_dropped += 1          
                    print("Simulated packet loss occurred, ignoring this packet's arrival")    
                    continue 
                if simulate_corrupt():                            
                    print("Corrupted packet checksum")                            
                    packArray = bytearray(pack_data)                            
                    packArray[-2] = 0x00                           
                    pack_data = bytes(packArray)
                # unpack packet header, data
                try:
                                    
                    seq, ack, pktType, payload, checksum = parse_packet(pack_data)
                    # calculate the packet checksum
                    newCheck = calculate_checksum(seq, ack, pktType, payload)
                    # if packet values are misaligned or imroperly built
                except ValueError:
                                
                    print(f"ValueError, malformed packet from sender {sender_addr}, dropping.")
                    #skip over packet
                    continue
                                
                # if data is inconsistent, skip packet    
                if not validChkSum(checksum, newCheck):
                            
                    print(f"Checksum not valid, data possibly lost in transfer for packet: {seq}, dropping")
                # increment packets dropped counter
                    packets_dropped += 1
                            
                    continue
                    # if sequence from parsed data is correct  
                if seq == expected_seq:
                    # if packet is carrying data
                    if pktType == TYPE_DATA:
                            # notify the terminal of the seq number
                        print(f"Seq num {seq} received")
                            # write the data received to the file
                        outfile.write(payload)
                            # increment packets received
                        packets_received += 1
                            # add payload len to total bytes received
                        bytes_received += len(payload)
                            # packet successfully received, update highest valid sequence
                        highest_seq = seq
                            # expect next packet sequence number
                        expected_seq = seq + 1
                    # if end packet received
                    elif pktType == TYPE_END:
                        # notify terminal of receieved packet
                        print(f"End packet received, transfer finished")
                        # set highest seq to this sequence
                        highest_seq = seq
                        # update transfer status tracker
                        fin_transfer = True
                        # break out of buffer reading loop
                        break
                        # if packet type is not DATA or END
                    else:
                        # notify terminal
                        print(f"Unexpected packet type {pktType} received, dropping")
                        # drop packet 
                        packets_dropped += 1
                        continue
                    # after all checks and counter adjustments to ensure correct packet transfer, send ack to sender
                    send_ack(sock, highest_seq, sender_addr)
                # if packet sequence does not match
                else:
                    # notify terminal
                    print(f"Out of order packet, dropping seq num {seq}")
                    # drop packet
                    packets_dropped += 1
                    continue
                
            # if no packet read from buffer
            if packedProcessing == False:
                    # sleep so that cpu is not running 100% in a super speed while loop
                    time.sleep(0.001)
                    # check if a timeout occurred
                    if time.time() - timeoutTime > LISTEN_TIMEOUT:
                        # notify terminal of timeout
                        print("Timeout, going back to listening for START packet")
                        # break out of loop to go back to listening for start
                        break
                    
                    continue
                        
            # summary of transfer from receiver side
        if outfile:
            duration = time.time() - start_time
            throughput = bytes_received/duration
            outfile.close()
            print(f"Finished transfer, Summary:\nDuration: {duration:.4f} Seconds\nFile Size: {filesize} Bytes\nAverage Throughput: {throughput/1024:.2f} KB/s\nLost Packets: {packets_dropped}")
            
                        
if __name__ == "__main__":
    
    active()
                    
                    
                    