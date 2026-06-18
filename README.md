# DATND Daikin DIII-Net / KNX UI v19

Fix KNX connect: XKNX start is now run as a background task so `/api/knx/connect` returns immediately and the UI status can become connected.

Run:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Check:

```text
/api/knx/status
```

Expected:

```json
"xknx_installed": true,
"real_knx_enabled": true,
"connected": true,
"xknx_task_running": true
```


## v21
- ACMode DPT changed to 20.105 for both KNX send and monitor decode.
- Monitor no longer guesses unknown 2-byte telegrams as DPT 9.001; unknown GA values are shown as raw bytes unless a GA -> DPT mapping is configured.


## v21
- Validate KNX 3-level group addresses before sending to the bus.
- Prevent misleading D3net -> KNX success log when GA is invalid.
- Show KNX address error for addresses like 1/8/4 because middle group must be 0..7.


## v22

- Added KNX -> D3net Control linking.
- KNX GroupValueWrite on configured Control GAs now writes to D3net holding registers:
  - ACSwitch On/off Control -> 42001 bit 0
  - ACTempSetpoint Setpoint Control -> 42003 signed x10
  - ACMode Mode Control DPT 20.105 -> 42002 bits 0..3
  - ACFan Fan Control DPT 5.001 -> 42001 bits 12..14
- Control telegrams are processed even when Monitor Log is disabled.
