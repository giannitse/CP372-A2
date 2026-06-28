# CP372 - Assignment 2

## Reliable Data Transfer over UDP

### Overview

This project implements two reliable data transfer protocols using Python UDP sockets:

- Stop-and-Wait Protocol
- Go-Back-N (GBN) Protocol

Because UDP does not guarantee reliable delivery, both protocols implement reliability mechanisms including:

- Sequence numbers
- Acknowledgments (ACKs)
- Timeouts
- Retransmissions
- Simulated packet loss

The Go-Back-N implementation also includes checksum-based error detection and optional packet corruption simulation.

The system transfers files between a sender and receiver while maintaining reliability despite packet loss and transmission errors.

---

## Requirements

### Software

- Python 3.x

### Libraries Used

The following standard Python libraries are used:

- socket
- struct
- os
- time
- random
- sys

No third-party libraries were used.

---

## Project Structure

project/

├── CP372_A2_Report.docx

├── gbn_receiver.py

├── gbn_sender.py

├── stopwait_receiver.py

├── stopwait_sender.py

├── README.md

└── received_files/

---

## Protocol Features

### Stop-and-Wait

The Stop-and-Wait implementation:

- Transfers files over UDP
- Uses one outstanding packet at a time
- Waits for an ACK before sending the next packet
- Retransmits packets after timeout
- Supports configurable packet loss simulation
- Uses START and END control packets for file transfer management

### Go-Back-N

The Go-Back-N implementation:

- Uses a sliding window protocol
- Window size configurable through WINDOW_SIZE
- Supports cumulative acknowledgments
- Retransmits all unacknowledged packets after timeout
- Supports packet loss simulation
- Supports packet corruption simulation
- Uses Internet-style checksum validation for error detection

---

## Packet Format

### Stop-and-Wait Packet Structure

Header Format:

|Field|Size|
|---|---|
|Sequence Number|4 bytes|
|ACK Number|4 bytes|
|Packet Type|1 byte|
|Payload Length|2 bytes|

Total Header Size: 11 bytes

Packet Types:

|Type|Value|
|---|---|
|DATA|0|
|ACK|1|
|START|2|
|END|3|

Payload Size:
1024 bytes per DATA packet

---

### Go-Back-N Packet Structure

Header Format:

|Field|Size|
|---|---|
|Sequence Number|4 bytes|
|ACK Number|4 bytes|
|Packet Type|1 byte|
|Payload Length|2 bytes|
|Checksum|2 bytes|

Total Header Size: 13 bytes

Additional Features:

- 16-bit checksum validation
- Corruption detection
- Cumulative ACK support

Payload Size:
2048 bytes per DATA packet

---

## Running the Programs

### Stop-and-Wait Receiver

Start the receiver:

```
python receiver_stopwait.py
```

Optional packet loss rate:

```
python receiver_stopwait.py 0.1
```

Example:

0.1 = 10% packet loss

---

### Stop-and-Wait Sender

Send a file:

```
python sender_stopwait.py filename.txt
```

If no file is specified:

```
python sender_stopwait.py
```

A 10 KB test file is automatically generated and transferred.

---

### Go-Back-N Receiver

Start the receiver:

```
python receiver_gbn.py
```

Packet loss and corruption rates can be modified inside the source file:

LOSS_RATE

CORRUPTION_RATE

---

### Go-Back-N Sender

Send a file:

```
python sender_gbn.py filename.txt
```

If no file is specified:

```
python sender_gbn.py
```

A 10 KB test file is automatically generated and transferred.

---

## Configuration

### Stop-and-Wait

|Setting|Value|
|---|---|
|Receiver Port|9000|
|Sender Port|9001|
|Payload Size|1024 bytes|
|Timeout|1.0 seconds|
|Max Retries|20|

### Go-Back-N

|Setting|Value|
|---|---|
|Receiver Port|9000|
|Sender Port|9001|
|Payload Size|2048 bytes|
|Window Size|4|
|Timeout|0.1 seconds|
|Max Retransmits|30|

---

## Packet Loss Simulation

The receiver can simulate packet loss using:

```
LOSS_RATE
```

Example:

```
LOSS_RATE = 0.10
```

Causes approximately 10% of packets to be discarded.
Dropped packets are recovered through retransmission by the sender.

---

## Packet Corruption Simulation

The Go-Back-N implementation supports packet corruption simulation.

Example:

```
CORRUPTION_RATE = 0.10
```

Corrupted packets fail checksum validation and are discarded by the receiver.
The sender eventually retransmits the lost packet after timeout.

---

## Output Statistics

At the end of each transfer, both sender and receiver display:

- Total file size
- Transfer duration
- Average throughput
- Number of retransmissions
- Number of dropped packets (receiver)

These statistics were used to compare protocol performance under different loss rates.

---

## Assumptions

- Sender and receiver are running on the same network.
- UDP packets may be lost but are not reordered frequently.
- Files fit into available memory and storage.
- Sequence numbers do not wrap around during testing.
- Only one file transfer is active at a time.
- Stop-and-Wait assumes strictly ordered delivery.

---

## Authors

Group Members:

- Gregory Lui - [luix5601@mylaurier.ca](mailto:luix5601@mylaurier.ca)
- Gianni Tse - [gtse4760@mylaurier.ca](mailto:gtse4760@mylaurier.ca)
- Robert Glennie - [glen7639@mylaurier.ca](mailto:glen7639@mylaurier.ca)
- Mohib Abbas - [abba9980@mylaurier.ca](mailto:abba9980@mylaurier.ca)
- Philip Marian - [mari8670@mylaurier.ca](mailto:mari8670@mylaurier.ca)

---

## Academic Integrity

This project was developed as part of CP372 – Computer Networks. All code was written by the group members in accordance with the course academic integrity policy.
