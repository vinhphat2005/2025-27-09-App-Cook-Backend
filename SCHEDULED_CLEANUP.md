# Scheduled Cleanup System

## Tổng quan

Hệ thống tự động xóa vĩnh viễn các món ăn đã được soft delete sau 7 ngày sử dụng **APScheduler**.

## Cách hoạt động

### 1. Auto Cleanup (Tự động - RECOMMENDED)

**APScheduler** chạy background job hàng ngày lúc **2:00 AM** để:
- Tìm các dishes có `deleted_at < (now - 7 days)`
- Xóa vĩnh viễn: Cloudinary images, comments, recipes, dish documents
- Ghi log cleanup statistics

**Setup:**
```bash
# Install dependency
pip install apscheduler==3.10.4

# Hoặc update requirements
pip install -r requirements.txt
```

**Cấu hình lịch trình:**
Trong `main_async.py`:
```python
scheduler.add_job(
    auto_cleanup_deleted_dishes,
    CronTrigger(hour=2, minute=0),  # 2:00 AM mỗi ngày
    id="cleanup_deleted_dishes",
    name="Cleanup dishes deleted >7 days ago",
    replace_existing=True
)
```

**Thay đổi lịch trình:**
- Mỗi giờ: `CronTrigger(minute=0)`
- Mỗi 6 giờ: `CronTrigger(hour='*/6')`
- Mỗi tuần (Chủ nhật 3 AM): `CronTrigger(day_of_week='sun', hour=3)`
- Mỗi tháng (ngày 1, 3 AM): `CronTrigger(day=1, hour=3)`

**Kiểm tra scheduler:**
```python
# Logs khi startup
✅ Background scheduler started - Daily cleanup at 2:00 AM

# Logs khi cleanup chạy
🗑️ Starting automatic cleanup of deleted dishes...
✅ Automatic cleanup completed: {'dishes_deleted': 5, 'images_deleted': 5, ...}
```

### 2. Manual Cleanup (Thủ công)

Vẫn có thể chạy cleanup thủ công qua API:

```bash
curl -X POST http://localhost:8000/dishes/admin/cleanup-deleted \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Response:**
```json
{
  "success": true,
  "cleanup_stats": {
    "dishes_deleted": 5,
    "images_deleted": 5,
    "comments_deleted": 12,
    "recipes_deleted": 5,
    "errors": []
  },
  "cutoff_date": "2025-10-21T00:00:00"
}
```

## Monitoring

### Check Scheduler Status

Thêm endpoint để check scheduler (optional):

```python
@app.get("/admin/scheduler/status")
async def get_scheduler_status():
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger)
            }
            for job in jobs
        ]
    }
```

### Logs

Kiểm tra logs để monitoring:
```bash
# Docker logs
docker logs backend-container -f | grep cleanup

# Local logs
tail -f backend.log | grep cleanup
```

## Production Deployment

### Docker/Kubernetes

Scheduler chạy trong container, không cần cron job riêng:
```yaml
# docker-compose.yml
services:
  backend:
    image: backend:latest
    environment:
      - TZ=Asia/Ho_Chi_Minh  # Set timezone
```

### Timezone Configuration

```python
# Sử dụng timezone cụ thể
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Vietnam timezone
vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')

scheduler.add_job(
    auto_cleanup_deleted_dishes,
    CronTrigger(hour=2, minute=0, timezone=vn_tz),
    id="cleanup_deleted_dishes"
)
```

### Multiple Instances (Load Balancing)

⚠️ **Quan trọng:** Khi chạy nhiều backend instances, chỉ 1 instance nên chạy scheduler.

**Giải pháp 1: Env Variable**
```python
# main_async.py
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"

if ENABLE_SCHEDULER and not scheduler.running:
    scheduler.add_job(...)
    scheduler.start()
```

**Giải pháp 2: Separate Scheduler Service**
```yaml
# docker-compose.yml
services:
  backend-api:
    image: backend:latest
    replicas: 3
    environment:
      - ENABLE_SCHEDULER=false
  
  backend-scheduler:
    image: backend:latest
    replicas: 1
    environment:
      - ENABLE_SCHEDULER=true
```

## Testing

### Test Cleanup Immediately

Chạy cleanup cho dishes > 1 minute (for testing):
```python
# Temporary test function
async def test_cleanup():
    cutoff_date = datetime.utcnow() - timedelta(minutes=1)
    # ... same cleanup logic
```

### Trigger Job Manually

```python
# Trong Python shell hoặc endpoint
from main_async import scheduler, auto_cleanup_deleted_dishes

# Run immediately
await auto_cleanup_deleted_dishes()

# Schedule to run in 10 seconds
from datetime import datetime, timedelta
scheduler.add_job(
    auto_cleanup_deleted_dishes,
    'date',
    run_date=datetime.now() + timedelta(seconds=10)
)
```

## Troubleshooting

### Scheduler không chạy

**Kiểm tra:**
1. ✅ APScheduler installed: `pip list | grep apscheduler`
2. ✅ Scheduler started: Check logs for "Background scheduler started"
3. ✅ No exceptions in startup_event
4. ✅ Timezone đúng

**Debug:**
```python
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('apscheduler').setLevel(logging.DEBUG)
```

### Job không execute

**Kiểm tra:**
1. ✅ Async function: `async def auto_cleanup_deleted_dishes()`
2. ✅ Import đúng collections
3. ✅ MongoDB connection active
4. ✅ Exceptions không bị swallow

### Multiple executions

**Nguyên nhân:** Multiple backend instances chạy scheduler

**Giải pháp:** Dùng distributed lock (Redis):
```python
async def auto_cleanup_deleted_dishes():
    # Acquire lock
    lock = await redis_client.set("cleanup_lock", "1", nx=True, ex=3600)
    if not lock:
        logging.info("Cleanup already running, skipping...")
        return
    
    try:
        # ... cleanup logic
    finally:
        await redis_client.delete("cleanup_lock")
```

## Alternative: External Cron Job

Nếu không dùng APScheduler, có thể dùng system cron:

```bash
# crontab -e
0 2 * * * curl -X POST http://localhost:8000/dishes/admin/cleanup-deleted \
  -H "Authorization: Bearer ADMIN_TOKEN"
```

**Nhược điểm:**
- Cần setup cron trên server
- Phải quản lý authentication token
- Khó scale với multiple servers

**Ưu điểm APScheduler:**
- ✅ Tự động với application
- ✅ No external dependencies
- ✅ Easy configuration
- ✅ Logs tập trung
- ✅ Works trong Docker containers

## Recommendation

🎯 **Production Setup:**
1. Dùng APScheduler với single scheduler instance
2. Enable scheduler qua env variable: `ENABLE_SCHEDULER=true`
3. Set đúng timezone: `TZ=Asia/Ho_Chi_Minh`
4. Monitor logs thường xuyên
5. Backup database trước khi cleanup (optional)

🎯 **Development:**
1. Set cleanup interval ngắn hơn để test (mỗi giờ)
2. Hoặc trigger manual cleanup qua API
3. Check logs để verify behavior
