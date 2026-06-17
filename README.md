# DATND Daikin DIII-Net + Virtual Modbus + KNX UI

## Run

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Web UI: `http://SERVER_IP:8080`

Login: `admin / admin`

Virtual Modbus TCP server: `SERVER_IP:1502`

## KNX Gateway Config

Menu Management now includes **KNX Gateway Config** with:

- Gateway name
- Gateway IP
- Gateway port, default `3671`
- Physical address, default `1.1.10`
- Protocol: Tunnel UDP / Tunnel TCP / Multicast
- Connect / Disconnect
- Monitor Log ON/OFF
- KNX Group Address Mapping per indoor
- KNX Monitor Log table similar to ETS Group Monitor

The KNX monitor UI/API is implemented. The current build uses an internal telegram buffer/demo loop so the web UI and configuration workflow are ready without requiring a KNX stack library. Real KNXnet/IP subscription can be attached behind the same `/api/knx/*` endpoints.

## Daikin register logic

- Connected indoor detection: input registers `30002-30005` bits.
- Capability: `31001 + index*3`.
- Status: `32001 + index*6`.
- Holding control: `42001 + index*3`.


## v12 changes
- Removed KNX Group Address Mapping panel.
- Renamed App Interface Config to Indoor Mapping Address.
- Added target Modify workflow with ACSwitch, ACTempSetpoint, ACTempAmbient, ACMode and ACFan KNX address fields.
