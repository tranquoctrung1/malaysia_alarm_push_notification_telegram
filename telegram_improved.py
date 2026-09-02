import asyncio
import json
import sys
import time
import os
from datetime import datetime
from contextlib import asynccontextmanager
import pyodbc
from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Bot
from telegram.error import TelegramError, RetryAfter
from loguru import logger
from dotenv import load_dotenv

# Load environment variables from .env next to the exe/script
_base_dir = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
load_dotenv(os.path.join(_base_dir, '.env'))

# --- Cấu hình từ Environment Variables ---
SQL_CONFIG = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={os.getenv('SQL_SERVER')};"
    f"DATABASE={os.getenv('SQL_DATABASE')};"
    f"UID={os.getenv('SQL_USER')};"
    f"PWD={os.getenv('SQL_PASSWORD')};"
    f"Connection Timeout=30;"
    f"TrustServerCertificate=yes;"
)
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('MONGO_DB_NAME', 'vilog_malaysia')
TG_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', "")
_exe_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
_json_db_raw = os.getenv('JSON_DB_PATH', 'last_index.json')
JSON_DB = _json_db_raw if os.path.isabs(_json_db_raw) else os.path.join(_exe_dir, _json_db_raw)
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', '120'))  # seconds
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))

# Setup logging với rotation và compression
logger.add(
    "logs/alarm_bot_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # Rotate hàng ngày
    retention="30 days",
    compression="zip",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)


class UtiliCoreStableBot:
    def __init__(self):
        # Validate required env vars
        if not TG_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN không được để trống trong .env")
        
        self.bot = Bot(token=TG_TOKEN)
        self.mg_client = None
        self.db = None
        self.sql_conn = None
        self.last_index = self.load_last_index()
        self.is_running = False
        self.health_check_time = time.time()
        
        logger.info("Bot được khởi tạo thành công")

    def load_last_index(self):
        """Load last processed alarm index từ JSON file"""
        try:
            if os.path.exists(JSON_DB):
                with open(JSON_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    index = data.get("last_index", 0)
                    logger.info(f"Loaded last_index: {index} từ {JSON_DB}")
                    return index
            else:
                logger.warning(f"File {JSON_DB} không tồn tại, bắt đầu từ index 0")
                return 0
        except Exception as e:
            logger.error(f"Lỗi đọc file JSON: {e}, bắt đầu từ index 0")
            return 0

    def save_last_index(self, index):
        """Lưu last processed index vào JSON file"""
        try:
            # Đảm bảo thư mục tồn tại
            os.makedirs(os.path.dirname(JSON_DB) if os.path.dirname(JSON_DB) else '.', exist_ok=True)
            
            with open(JSON_DB, 'w', encoding='utf-8') as f:
                json.dump({
                    "last_index": index,
                    "updated_at": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Lỗi ghi file JSON: {e}")

    async def connect_mongodb(self):
        """Kết nối MongoDB với error handling"""
        try:
            if self.mg_client is None:
                self.mg_client = AsyncIOMotorClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=5000,
                    maxPoolSize=10
                )
                # Test connection
                await self.mg_client.admin.command('ping')
                self.db = self.mg_client[DB_NAME]
                logger.info("✅ Kết nối MongoDB thành công")
                return True
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối MongoDB: {e}")
            self.mg_client = None
            self.db = None
            return False

    def connect_sql(self):
        """Kết nối SQL Server với connection pooling"""
        try:
            if self.sql_conn is None or not self._is_sql_alive():
                self.sql_conn = pyodbc.connect(SQL_CONFIG)
                logger.info("✅ Kết nối SQL Server thành công")
            return self.sql_conn
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối SQL Server: {e}")
            self.sql_conn = None
            return None

    def _is_sql_alive(self):
        """Kiểm tra SQL connection còn sống không"""
        try:
            if self.sql_conn:
                cursor = self.sql_conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return True
        except:
            return False

    async def get_target_chat_ids(self, device_id):
        """Lấy danh sách chat_id cần gửi alarm cho device_id"""
        if self.db is None:
            logger.error("MongoDB chưa kết nối")
            return []
        
        chat_ids = []
        try:
            d_id = int(device_id)
            pipeline = [
                        {"$match": {
                            "$or": [
                                # Trường hợp 1: Nằm trong khoảng start/end (bất kể isCheckList)
                                {
                                    "start": {"$lte": d_id},
                                    "end": {"$gte": d_id}
                                },
                                # Trường hợp 2: Nằm trong listSiteId và isCheckList = true
                                {
                                    "isCheckList": True,
                                    "listSiteId": {
                                        "$regex": f"(^|,)\\s*{d_id}\\s*(,|$)"
                                    }
                                }
                            ]
                        }},
                        {"$lookup": {
                            "from": "t_telegram_ranges",
                            "localField": "_id",
                            "foreignField": "rangeId",
                            "as": "map"
                        }},
                        {"$unwind": "$map"},
                        {"$lookup": {
                            "from": "t_telegrams",
                            "localField": "map.telegramId",
                            "foreignField": "_id",
                            "as": "user"
                        }},
                        {"$unwind": "$user"},
                        {"$project": {"chat_id": "$user.chatId"}}
                    ]
            
            cursor = self.db.t_ranges.aggregate(pipeline)
            async for doc in cursor:
                if "chat_id" in doc:
                    chat_ids.append(doc["chat_id"])
            
            # Remove duplicates
            chat_ids = list(set(chat_ids))
            logger.debug(f"Device {device_id} -> {len(chat_ids)} chat_ids")
            
        except Exception as e:
            logger.error(f"Lỗi truy vấn MongoDB Mapping (Device {device_id}): {e}")
        
        return chat_ids

    async def get_all_chat_ids(self):
        """Lấy toàn bộ chat_id có trong hệ thống (t_telegrams)"""
        if self.db is None:
            return []
        try:
            cursor = self.db.t_telegrams.find({}, {"chatId": 1})
            ids = []
            async for doc in cursor:
                if "chatId" in doc:
                    ids.append(doc["chatId"])
            return list(set(ids))
        except Exception as e:
            logger.error(f"Lỗi lấy toàn bộ chat_id: {e}")
            return []

    async def fetch_sql_alarms(self):
        """Lấy alarm từ SQL Server với retry mechanism"""
        for attempt in range(MAX_RETRIES):
            try:
                conn = self.connect_sql()
                if not conn:
                    raise Exception("Không thể kết nối SQL Server")
                
                cursor = conn.cursor()
                query = """
                    SELECT A.AlarmIndex, A.AlarmTime, S.Name, A.Description, A.HighPriority, A.Id
                    FROM [UtiliCore].[dbo].[ALARMLOG] A
                    LEFT JOIN [UtiliCore].[dbo].[SITELIST] S ON A.Id = S.Id
                    WHERE A.AlarmIndex > ?
                    ORDER BY A.AlarmIndex ASC
                """
                cursor.execute(query, (self.last_index,))
                rows = cursor.fetchall()
                
                alarms = []
                for r in rows:
                    #des = r[3].replace('HIGH', 'Urgent').replace('High', 'Urgent')
                    des = r[3]
                    
                    alarms.append({
                        "index": r[0],
                        "time": r[1],
                        "site": r[2] or "N/A",
                        "desc": des or "Không có mô tả",
                        "priority": r[4],
                        "device_id": r[5]
                    })
                
                cursor.close()
                return alarms
                
            except Exception as e:
                logger.warning(f"Lần thử {attempt + 1}/{MAX_RETRIES} lỗi SQL: {e}")
                self.sql_conn = None  # Force reconnect
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(5)
        
        logger.error("❌ Không thể lấy dữ liệu từ SQL sau nhiều lần thử")
        return []

    async def send_telegram_safe(self, chat_id, message, _retry=0):
        """Gửi tin nhắn Telegram với rate limiting và error handling"""
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            await asyncio.sleep(0.5)  # 500ms delay giữa các tin
            return True
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"Flood control tới {chat_id}: chờ {wait}s")
            if wait > 30:
                logger.error(f"Flood wait {wait}s quá lớn, skip msg tới {chat_id}")
                return False
            await asyncio.sleep(wait)
            if _retry < MAX_RETRIES:
                return await self.send_telegram_safe(chat_id, message, _retry + 1)
            logger.error(f"Hết retry sau flood control tới {chat_id}")
            return False
        except TelegramError as e:
            logger.error(f"Lỗi gửi Telegram tới {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Lỗi không xác định khi gửi tới {chat_id}: {e}")
            return False

    async def process_alarms(self, alarms):
        """Xử lý và gửi danh sách alarms"""
        success_count = 0
        failed_count = 0
        
        all_chat_ids = await self.get_all_chat_ids()

        for alarm in alarms:
            try:
                chat_ids = await self.get_target_chat_ids(alarm['device_id'])
                
                if not chat_ids:
                    logger.warning(f"⚠️ Alarm {alarm['index']} (Device {alarm['device_id']}): Không tìm thấy chat_id nào — không gửi thông báo")
                    self.last_index = alarm['index']
                    self.save_last_index(self.last_index)
                    continue
                
                # Format message
                priority_tag = "🔴 <b>Urgent</b>" if alarm['priority'] else "⚪ Normal"
                alarm_time = alarm['time'].strftime('%H:%M:%S %d/%m/%Y') if isinstance(alarm['time'], datetime) else str(alarm['time'])
                print(priority_tag)
                
                msg = (
                    f"🚨 <b>Alarm WaterCore System</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🆔 Site ID: <code>{alarm['device_id']}</code>\n"
                    f"📍 Site Name: <b>{alarm['site']}</b>\n"
                    f"📄 Description: {alarm['desc']}\n"
                    f"📊 Priority: {priority_tag}\n"
                    f"⏰ Alarm Time: {alarm_time}"
                )
                
                # Gửi tới tất cả chat_ids
                sent_ids = []
                failed_ids = []
                for cid in chat_ids:
                    if await self.send_telegram_safe(cid, msg):
                        sent_ids.append(cid)
                    else:
                        failed_ids.append(cid)

                logger.info(f"✅ Alarm {alarm['index']}: Gửi thành công tới {len(sent_ids)}/{len(chat_ids)} chat_id: {sent_ids}")
                if failed_ids:
                    logger.warning(f"⚠️ Alarm {alarm['index']}: Gửi thất bại tới {len(failed_ids)} chat_id: {failed_ids}")
                unassigned_ids = [cid for cid in all_chat_ids if cid not in chat_ids]
                if unassigned_ids:
                    logger.info(f"ℹ️ Alarm {alarm['index']}: {len(unassigned_ids)} chat_id tồn tại nhưng không được phân vào range của Device {alarm['device_id']}: {unassigned_ids}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"Lỗi xử lý alarm {alarm.get('index', 'unknown')}: {e}")
                failed_count += 1
            
            finally:
                # Luôn cập nhật index để không bị stuck
                self.last_index = alarm['index']
                self.save_last_index(self.last_index)
        
        return success_count, failed_count

    async def health_check(self):
        """Kiểm tra trạng thái hệ thống"""
        status = {
            "mongodb": "❌",
            "sql": "❌",
            "telegram": "❌",
            "last_index": self.last_index,
            "uptime": time.time() - self.health_check_time
        }
        
        # Check MongoDB
        try:
            if self.db:
                await self.db.command('ping')
                status["mongodb"] = "✅"
        except:
            pass
        
        # Check SQL
        if self._is_sql_alive():
            status["sql"] = "✅"
        
        # Check Telegram
        try:
            await self.bot.get_me()
            status["telegram"] = "✅"
        except:
            pass
        
        return status

    async def start_monitoring(self):
        """Main monitoring loop"""
        logger.info("="*50)
        logger.info("🚀 HỆ THỐNG BẮT ĐẦU CHẠY")
        logger.info(f"📍 Quét từ Index: {self.last_index}")
        logger.info(f"⏱️  Chu kỳ quét: {SCAN_INTERVAL}s")
        logger.info("="*50)
        
        # Kết nối MongoDB
        if not await self.connect_mongodb():
            logger.critical("❌ Không thể kết nối MongoDB. Bot dừng.")
            return
        
        # Kết nối SQL
        if not self.connect_sql():
            logger.critical("❌ Không thể kết nối SQL Server. Bot dừng.")
            return
        
        self.is_running = True
        loop_count = 0
        
        while self.is_running:
            loop_count += 1
            start_time = time.time()
            
            try:
                # Health check mỗi 10 lần loop
                if loop_count % 10 == 0:
                    health = await self.health_check()
                    logger.info(f"🏥 Health Check: MongoDB {health['mongodb']}, SQL {health['sql']}, Telegram {health['telegram']}")
                
                # Fetch alarms
                new_alarms = await self.fetch_sql_alarms()
                
                if new_alarms:
                    logger.info(f"🔔 Phát hiện {len(new_alarms)} báo động mới")
                    success, failed = await self.process_alarms(new_alarms)
                    logger.info(f"✅ Đã xử lý: {success} thành công, {failed} thất bại. Index mới: {self.last_index}")
                else:
                    logger.debug(f"✓ Không có alarm mới (Loop #{loop_count})")
                
            except Exception as e:
                logger.error(f"❌ Lỗi trong monitoring loop: {e}", exc_info=True)
            
            # Tính thời gian sleep để đảm bảo chu kỳ ổn định
            elapsed = time.time() - start_time
            sleep_time = max(1, SCAN_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Đang dừng bot...")
        self.is_running = False
        
        # Close connections
        if self.mg_client:
            self.mg_client.close()
            logger.info("✅ Đã đóng MongoDB connection")
        
        if self.sql_conn:
            self.sql_conn.close()
            logger.info("✅ Đã đóng SQL connection")
        
        logger.info("👋 Bot đã dừng hoàn toàn")


async def main():
    """Main entry point"""
    bot = UtiliCoreStableBot()
    
    try:
        await bot.start_monitoring()
    except KeyboardInterrupt:
        logger.info("⚠️  Nhận tín hiệu dừng từ người dùng (Ctrl+C)")
    except Exception as e:
        logger.critical(f"💥 Bot dừng do lỗi nghiêm trọng: {e}", exc_info=True)
    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
