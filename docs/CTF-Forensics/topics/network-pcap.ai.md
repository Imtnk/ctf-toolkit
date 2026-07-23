# Network / Packet Analysis (pcap)

You get a `.pcap` / `.pcapng` — a recording of network traffic. The flag is in a transferred file, an HTTP request, a DNS query, or a reassembled stream.

## First moves

```bash
file capture.pcap
capinfos capture.pcap            # summary: packet count, protocols, duration
strings -a capture.pcap | grep -i flag   # always try the cheap win first
```

Then open in **Wireshark** (GUI). Key features:

- **Statistics → Protocol Hierarchy** — what protocols are present? HTTP? FTP? DNS? TLS?
- **Statistics → Conversations** — who talked to whom, how much data.
- **Follow → TCP/HTTP Stream** (right-click a packet) — reassembles a whole conversation into readable text. This is where most flags are.
- **File → Export Objects → HTTP/SMB/…** — pull out transferred files (images, zips, docs) directly.

## tshark (CLI — scriptable)

```bash
tshark -r capture.pcap -Y http.request           # filter HTTP requests
tshark -r capture.pcap -Y 'dns' -T fields -e dns.qry.name  # exfil via DNS?
tshark -r capture.pcap -Y 'ftp' -T fields -e ftp.request.command -e ftp.request.arg
tshark -r capture.pcap --export-objects http,out/   # dump HTTP files
```

## What to look for by protocol

| Protocol | Trick |
|---|---|
| **HTTP** | Follow stream; check POST bodies, cookies, User-Agent; export transferred files |
| **FTP** | Credentials sent in cleartext; `RETR` shows downloaded files (data on FTP-DATA channel) |
| **DNS** | Exfiltration: long/weird subdomains are base64/hex chunks — concatenate & decode |
| **ICMP** | Data smuggled in ping payloads — check the packet data field |
| **TLS/HTTPS** | Encrypted. Need the key: look for a provided `sslkeylog.txt` / private key, then Wireshark → Preferences → TLS |
| **SMB** | Export files; look for shares and transferred docs |
| **Telnet** | Keystrokes in cleartext — Follow stream to read the session |

## Common patterns

- **Credentials in cleartext** (FTP/HTTP/Telnet) → Follow stream.
- **Exfil over DNS/ICMP** → collect the odd payloads, concatenate, base64/hex-decode (CyberChef Magic).
- **A file was downloaded** → Export Objects, then run [[file-analysis.ai]] on it (it might itself be stego/an archive).
- **USB pcap** (`usb.capdata`) → keyboard HID captures; decode scancodes to keystrokes with a known mapping script.

## Workflow

1. `capinfos` + `strings | grep flag`.
2. Protocol Hierarchy → pick the interesting protocol.
3. Follow the relevant stream / Export Objects.
4. Decode anything encoded → [[01-methodology.ai]] Step 5.
