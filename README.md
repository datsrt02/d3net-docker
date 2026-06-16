# Daikin DIII-Net Docker Modbus Server

Standalone Docker app:

- Web UI: http://HOST:8080
- Virtual Modbus TCP server: HOST:1502
- Upstream Daikin DIII Modbus gateway: configured in Web UI

Register addressing uses zero-based Modbus addressing internally:

- 30001 => input address 0
- 31001 => input address 1000
- 32001 => input address 2000
- 42001 => holding address 2000

Run:

```bash
docker compose up -d --build
```

In Modbus Poll, connect to port 1502. Use function 04 for input registers and function 03/06/16 for holding registers.
