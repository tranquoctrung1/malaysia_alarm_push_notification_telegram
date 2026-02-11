# UtiliCore Telegram Alarm Bot - Phiên bản cải tiến

## 🎯 Những cải tiến chính

### ✅ Bảo mật
- **Environment Variables**: Tất cả credentials được lưu trong file `.env`
- **Không hardcode**: Token, passwords không còn trong code
- **Git-safe**: File `.env` sẽ được gitignore

### ✅ Quản lý kết nối
- **Connection Pooling**: SQL connection được tái sử dụng
- **Health Check**: Tự động kiểm tra kết nối MongoDB, SQL, Telegram
- **Auto Reconnect**: Tự động kết nối lại khi mất kết nối
- **Graceful Shutdown**: Đóng connection đúng cách khi dừng

### ✅ Error Handling
- **Retry Mechanism**: Tự động thử lại khi lỗi SQL/MongoDB
- **Never Stuck**: Luôn cập nhật last_index để không bị kẹt
- **Detailed Logging**: Log chi tiết với rotation và compression
- **Exception Safety**: Bắt tất cả lỗi có thể xảy ra

### ✅ Performance
- **Efficient MongoDB Query**: Sử dụng aggregation pipeline tối ưu
- **Rate Limiting**: Tránh bị Telegram block
- **Configurable Scan Interval**: Có thể điều chỉnh chu kỳ quét

### ✅ Monitoring & Debugging
- **Health Check**: Kiểm tra định kỳ trạng thái hệ thống
- **Structured Logging**: Log theo ngày, tự động compress
- **Statistics**: Đếm success/failed cho mỗi batch

---

## 📦 Cài đặt

### 1. Clone code và cài dependencies

```bash
# Tạo virtual environment
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate  # Windows

# Cài đặt dependencies
pip install -r requirements.txt
```

### 2. Cấu hình môi trường

```bash
# Copy file mẫu
cp .env.example .env

# Chỉnh sửa file .env với thông tin thực tế
nano .env
```

**Lưu ý quan trọng**: 
- Đảm bảo file `.env` có quyền đọc đúng: `chmod 600 .env`
- **KHÔNG BAO GIỜ** commit file `.env` lên Git
- Thêm `.env` vào `.gitignore`

### 3. Cấu trúc thư mục

```
your-project/
├── telegram_improved.py
├── requirements.txt
├── .env
├── .env.example
├── last_index.json        # Tự động tạo
└── logs/                  # Tự động tạo
    └── alarm_bot_2024-XX-XX.log
```

---

## 🚀 Chạy bot

### Chạy thử nghiệm (development)

```bash
python telegram_improved.py
```

### Chạy như service (production)

#### Trên Linux với systemd:

```bash
# 1. Chỉnh sửa file telegram-bot.service
# - Thay your_username bằng user của bạn
# - Thay /path/to/your/bot bằng đường dẫn thực tế
# - Thay /path/to/your/venv/bin bằng đường dẫn venv thực tế

# 2. Copy service file
sudo cp telegram-bot.service /etc/systemd/system/

# 3. Reload systemd
sudo systemctl daemon-reload

# 4. Enable service (tự động chạy khi boot)
sudo systemctl enable telegram-bot

# 5. Start service
sudo systemctl start telegram-bot

# 6. Kiểm tra trạng thái
sudo systemctl status telegram-bot

# 7. Xem logs
sudo journalctl -u telegram-bot -f
```

### Với Docker (tùy chọn)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install ODBC Driver for SQL Server
RUN apt-get update && apt-get install -y \
    curl apt-transport-https gnupg2 \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY telegram_improved.py .

CMD ["python", "telegram_improved.py"]
```

```bash
# Build
docker build -t telegram-alarm-bot .

# Run
docker run -d \
  --name telegram-bot \
  --env-file .env \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/last_index.json:/app/last_index.json \
  telegram-alarm-bot
```

---

## 🔧 Cấu hình nâng cao

### Các biến môi trường trong `.env`:

| Biến | Mô tả | Mặc định |
|------|-------|----------|
| `SCAN_INTERVAL` | Chu kỳ quét alarm (giây) | 120 |
| `MAX_RETRIES` | Số lần retry khi lỗi SQL | 3 |
| `JSON_DB_PATH` | Đường dẫn file lưu index | last_index.json |

### Logging

Logs được lưu tự động trong thư mục `logs/`:
- Rotate: Hàng ngày lúc 00:00
- Retention: Giữ 30 ngày
- Compression: Tự động nén thành .zip

---

## 📊 Monitoring

### Kiểm tra Health Check

Bot tự động log health check mỗi 10 lần loop:

```
🏥 Health Check: MongoDB ✅, SQL ✅, Telegram ✅
```

### Các chỉ số cần theo dõi:

1. **MongoDB connection**: Nếu thấy ❌, kiểm tra MongoDB có chạy không
2. **SQL connection**: Nếu thấy ❌, kiểm tra SQL Server
3. **Telegram connection**: Nếu thấy ❌, kiểm tra token và network

### Log files

```bash
# Xem log realtime
tail -f logs/alarm_bot_$(date +%Y-%m-%d).log

# Search lỗi
grep "ERROR" logs/*.log

# Đếm số alarm đã gửi
grep "✅ Alarm" logs/*.log | wc -l
```

---

## 🐛 Troubleshooting

### Bot không gửi được tin nhắn

1. Kiểm tra Telegram token:
```bash
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

2. Kiểm tra chat_id mapping trong MongoDB:
```javascript
// Trong MongoDB shell
use bavitech_db
db.ranges.find()
db.t_telegrams.find()
```

### SQL Server timeout

- Tăng `Connection Timeout` trong `.env`
- Kiểm tra firewall/network
- Verify SQL credentials

### MongoDB connection failed

```bash
# Test MongoDB connection
mongo --host localhost --port 27017

# Check MongoDB service
sudo systemctl status mongodb
```

### Bot bị kẹt ở một index

- Kiểm tra file `last_index.json`
- Có thể xóa file này để reset về 0
- Hoặc chỉnh sửa manual:
```json
{
  "last_index": 12345,
  "updated_at": "2024-01-01T00:00:00"
}
```

---

## 🔒 Security Checklist

- [ ] File `.env` đã được thêm vào `.gitignore`
- [ ] File `.env` có quyền `chmod 600`
- [ ] SQL password đã được thay đổi so với mặc định
- [ ] Telegram bot token được giữ bí mật
- [ ] MongoDB có authentication (nếu expose ra internet)
- [ ] Chỉ cho phép IP cần thiết connect vào SQL Server

---

## 📝 Changelog so với phiên bản cũ

### Added
- ✅ Environment variables cho tất cả config
- ✅ Health check định kỳ
- ✅ Graceful shutdown
- ✅ Better logging với rotation
- ✅ Connection pooling
- ✅ Auto reconnect
- ✅ Statistics tracking

### Fixed
- ✅ Missing `time` import
- ✅ MongoDB connection leak
- ✅ SQL connection không được đóng
- ✅ Bot có thể bị stuck ở một index
- ✅ Không handle Telegram rate limit đúng cách

### Changed
- ✅ Cấu trúc code rõ ràng hơn
- ✅ Error handling toàn diện
- ✅ Logging format chuẩn hơn

---

## 📞 Support

Nếu gặp vấn đề:
1. Kiểm tra logs trong thư mục `logs/`
2. Chạy health check manual
3. Verify tất cả credentials trong `.env`
4. Check MongoDB/SQL/Telegram connectivity

---

## 📄 License

Mã nguồn này dành riêng cho dự án UtiliCore của BaviTech.
