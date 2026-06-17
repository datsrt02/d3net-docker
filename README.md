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


## v20
- ACMode DPT changed to 20.105 for both KNX send and monitor decode.
- Monitor no longer guesses unknown 2-byte telegrams as DPT 9.001; unknown GA values are shown as raw bytes unless a GA -> DPT mapping is configured.
