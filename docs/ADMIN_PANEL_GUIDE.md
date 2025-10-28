# 🔐 Admin Panel - Hướng Dẫn Sử Dụng

## ✅ Tính năng đã hoàn thành

### Backend
- ✅ `/users/me/is-admin` - Check admin role
- ✅ `/users/admin/cleanup` - Cleanup invalid dishes  
- ✅ `/users/admin/cleanup-deleted` - Permanently delete old dishes
- ✅ `/users/admin/migrate-difficulty` - Migrate difficulty field
- ✅ `/users/admin/migrate-images` - Migrate images to Cloudinary

### Frontend  
- ✅ `useAdmin()` hook - Check admin status
- ✅ Admin Panel screen (`/admin-panel`)
- ✅ Admin button in Profile tab (shield icon)
- ✅ Automatic access control

---

## 🚀 Cách sử dụng

### 1. Set quyền Admin cho user

```bash
# Từ thư mục backend
cd d:\VSCodeProjects\CookAppBackendORIGINALUSETHIS\2025-27-09-App-Cook-Backend

# Set admin bằng email
python scripts/set_firebase_admin_claim.py --email yourname@gmail.com --admin true

# Hoặc set bằng UID
python scripts/set_firebase_admin_claim.py --uid abc123xyz --admin true
```

### 2. Login lại vào App

⚠️ **QUAN TRỌNG:** Sau khi set admin claim, user **PHẢI đăng xuất và đăng nhập lại** để Firebase token được refresh với claims mới.

### 3. Sử dụng Admin Panel

1. Mở app → Vào tab **Profile**
2. Nếu là admin, sẽ thấy icon **🛡️ (shield)** bên cạnh nút edit profile
3. Nhấn vào icon shield → Vào **Admin Panel**
4. Chọn action muốn thực hiện:
   - **🧹 Cleanup Invalid Dishes** - Xóa dishes không hợp lệ
   - **🗑️ Permanently Delete Old Dishes** - Xóa vĩnh viễn dishes đã soft-delete > 7 ngày
   - **🔄 Migrate Difficulty** - Di chuyển difficulty từ recipes sang dishes
   - **📸 Migrate Images** - Migrate ảnh từ base64 sang Cloudinary

---

## 🔍 Kiểm tra Admin Status

### Từ Backend Logs
```bash
# Xem audit log
Get-Content scripts\logs\admin_claims_audit.log -Tail 20
```

### Từ Firebase Console
1. Vào [Firebase Console](https://console.firebase.google.com/)
2. Authentication → Users
3. Click vào user → Xem Custom Claims
4. Sẽ thấy `{"admin": true}`

### Từ App (Debug)
```typescript
// Trong useAdmin hook
const { isAdmin, loading } = useAdmin();
console.log('Is Admin:', isAdmin);
```

---

## 📱 UI Flow

```
Profile Tab
└── Nếu là admin
    └── Hiển thị Admin Panel button (shield icon)
        └── Nhấn vào
            └── Mở Admin Panel Screen
                ├── Warning Banner
                ├── 4 Admin Actions (với confirmation)
                └── Info Section
```

---

## 🔒 Security

### Backend
- ✅ Tất cả admin endpoints đều kiểm tra `is_admin()`
- ✅ 4 cấp độ kiểm tra:
  1. DEBUG mode (development only)
  2. Firebase custom claims (`admin: true`)
  3. ADMIN_EMAILS từ .env
  4. `role: 'admin'` trong MongoDB

### Frontend
- ✅ Admin button chỉ hiển thị nếu `isAdmin === true`
- ✅ Admin Panel tự động redirect nếu không phải admin
- ✅ Confirmation dialog cho các hành động nguy hiểm

---

## 🛠️ Troubleshooting

### Admin button không hiện

**Nguyên nhân:**
- Chưa set admin claim
- Chưa login lại sau khi set claim
- Token chưa được refresh

**Giải pháp:**
```bash
# 1. Verify admin claim đã set
python scripts/set_firebase_admin_claim.py --email yourname@gmail.com --admin true

# 2. Đăng xuất và đăng nhập lại
# 3. Clear app cache nếu cần
```

### API Error "Admin access required"

**Nguyên nhân:**
- Token không có admin claim
- Backend không nhận diện được admin

**Giải pháp:**
```bash
# Check backend logs
uvicorn main_async:app --reload

# Test endpoint trực tiếp
curl -H "Authorization: Bearer <token>" http://localhost:8000/users/me/is-admin
```

### Actions không hoạt động

**Nguyên nhân:**
- Không có kết nối mạng
- Backend không chạy
- Token hết hạn

**Giải pháp:**
- Kiểm tra backend đang chạy
- Check network connection
- Login lại để refresh token

---

## 📊 Testing

### Manual Test Checklist

- [ ] Set admin claim cho user
- [ ] Login lại
- [ ] Thấy admin button trong Profile
- [ ] Nhấn vào admin button
- [ ] Admin Panel screen mở
- [ ] Warning banner hiển thị
- [ ] 4 actions hiển thị
- [ ] Nhấn vào action → Confirmation dialog
- [ ] Confirm → Loading indicator
- [ ] Success → Alert với kết quả
- [ ] Error handling hoạt động đúng

### API Test

```bash
# Get token from app
TOKEN="your-firebase-token"

# Test check admin
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/users/me/is-admin

# Test cleanup
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/users/admin/cleanup
```

---

## 📝 Notes

- Admin Panel đã được tích hợp hoàn toàn
- Tất cả actions đều có confirmation
- Loading states và error handling đầy đủ
- Audit logging cho mọi thay đổi
- Frontend tự động ẩn/hiện dựa trên admin status

---

## 🎯 Next Steps (Optional)

1. **Statistics Dashboard** - Hiển thị thống kê hệ thống
2. **User Management** - Quản lý users từ admin panel
3. **Content Moderation** - Duyệt/xóa nội dung vi phạm
4. **Notification Center** - Gửi thông báo hệ thống
5. **Analytics** - Xem metrics và logs

---

**Tác giả:** AI Assistant  
**Ngày tạo:** 2025-10-28  
**Version:** 1.0
