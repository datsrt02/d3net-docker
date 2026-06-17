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


## v13 changes
- Removed KNX Group Address Mapping panel.
- Renamed App Interface Config to Indoor Mapping Address.
- Added target Modify workflow with ACSwitch, ACTempSetpoint, ACTempAmbient, ACMode and ACFan KNX address fields.


## v13 changes
- Modify Target now opens as a separate page while keeping the left menu.
- Added Back button to return to Indoor Mapping Address.
- ACSwitch, ACTempSetpoint, ACTempAmbient, ACMode, ACFan are accordion rows; click each row to expand/collapse KNX Address fields.


## v14
- Update buttons in ACSwitch/ACTempSetpoint/ACTempAmbient/ACMode/ACFan show inline Saved text for 2 seconds.


## v15 - D3net to KNX auto link

This version automatically links configured Indoor Mapping Address targets to KNX status group addresses on each UI refresh.

For each target, values are decoded from DIII-Net status registers using the following rules for indoor `1-00` and the same `+6 registers` step for following indoors:

- On/off Status: `32001 bit 0` -> KNX DPT `1.001`, value `0/1`
- Setpoint Status: `32003` signed x10 -> KNX DPT `9.001`
- Status Ambient: `32005` signed x10 -> KNX DPT `9.001`
- Mode Status: `32002 bits 0..3` -> `{0:9, 1:1, 2:3, 3:0, 7:14}`
- Fan Status: `32001 bits 12..14` -> `{0:0, 1/2:85, 3:170, 4/5:255}`

The current KNX runtime records these outgoing values in the KNX Monitor Log and de-duplicates unchanged values.

## v16 KNX real bus sender

This version installs `xknx` and changes KNX Runtime from UI-only logs to real KNXnet/IP GroupValueWrite sender.

D3net -> KNX status writes use these DPTs:

- On/Off Status: DPT 1.001
- Setpoint Status: DPT 9.001
- Ambient Status: DPT 9.001
- Mode Status: DPT 5.010 byte value
- Fan Status: DPT 5.001 percentage byte

After KNX Gateway Config -> Connect, `/api/knx/status` should show:

```json
"xknx_installed": true,
"real_knx_enabled": true,
"connected": true
```
