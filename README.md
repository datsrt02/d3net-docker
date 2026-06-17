# Daikin DIII-Net Docker Modbus Server - DATND Style UI

Bản Docker này tách phần lõi D3net ra khỏi Home Assistant và bổ sung giao diện web dạng DATND/HBS như video mẫu:

- Login local
- Menu trái dạng cây: Monitoring, Module Daikin HBS, App Interface Config, Area/Floor/Room, Register Map, Logs
- Cấu hình upstream DIII/Modbus gateway: IP, port, slave ID, TCP/RTU over TCP
- Scan/Connect để đọc danh sách indoor 1-00 ... 4-15
- Dashboard điều khiển indoor: ON/OFF, mode, setpoint
- Cấu hình giao diện app: target, object, icon, room, bind indoor
- Virtual Modbus TCP server xuất register input/holding theo mapping Daikin Modbus Interface DIII

## Chạy Docker

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Truy cập web:

```text
http://IP_SERVER:8080
```

Login mặc định:

```text
admin / admin
```

Virtual Modbus TCP:

```text
IP_SERVER:1502
```

## Register chính

- 30001 -> input address 0
- 30002-30005 -> connected indoor status
- 31001 + index*3 -> capability
- 32001 + index*6 -> status/power/fan
- 32002 + index*6 -> mode/filter/status
- 32003 + index*6 -> setpoint x10
- 32005 + index*6 -> room temperature x10
- 42001 + index*3 -> holding power/fan
- 42002 + index*3 -> holding mode/filter reset
- 42003 + index*3 -> holding setpoint x10

## Lưu ý

Giao diện Area/Room/App Device hiện lưu bằng localStorage của trình duyệt để mô phỏng phần cấu hình app trong video. Phần kết nối Daikin thật vẫn dùng API backend và D3netGateway.


## v4 changes
- Removed duplicated System Setting menu group.
- Replaced KANONBUS logo text with DATND.

## v5 fix
- Added strict validation for Gateway Port, Slave ID and Virtual Modbus Port.
- Added register-address guard in D3netGateway.
- If API returns `0 <= address < 65535`, check that Gateway Port is `502` and Slave ID is `1..247`; do not enter register numbers such as 30001/42001 in those fields.


## Debug discovery
Sau khi bấm Start, mở: /api/debug/system để xem raw 30001-30009 gateway trả về. Mở /api/debug/unit/1-00 để xem raw 31001-31003, 32001-32006, 33601-33602.

## v7 note
- Discovery now uses 30002-30005 as the source of truth. If 310xx/320xx are temporarily unreadable, the indoor is still displayed and refreshed later.
