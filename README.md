# DATND Daikin DIII-Net / KNX UI v24

Modernized UI while keeping the existing functions and menu structure:

- Overview Dashboard
- Modbus Gateway Config
- KNX Gateway Config
- Indoor Mapping Address
- Area / Room
- Register Map
- Logs

Run:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

Open: `http://SERVER_IP:8080`

Default login: `admin / admin`

## v26
- Fixed login button issue caused by DOM id/function name collision (`login`).

## v27
- Replaced top-right D logo with user icon menu.
- Added Admin user dropdown with Change Password and Logout.
- Added backend password storage in /app/data/users.json using PBKDF2-SHA256.
- Updated Dockerfile pip install step to use Aliyun mirror with cache mount.
