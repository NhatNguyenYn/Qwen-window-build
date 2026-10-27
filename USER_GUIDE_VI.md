# Hướng dẫn sử dụng Qwen Desktop Chat

Tài liệu này dành cho người dùng **không cần biết lập trình**. Bạn chỉ cần làm theo đúng
các bước dưới đây là chạy được ứng dụng.

---

## 1. Xác định thư mục dự án

Thư mục dự án là nơi chứa các file sau:

```
main.py
run.bat
setup.bat
requirements.txt
app\
tests\
```

Trong tài liệu này, mọi lệnh đều được chạy **trong thư mục đó**. Nếu bạn không chắc,
xem đường dẫn ở thanh địa chỉ của File Explorer khi mở thư mục.

> Ghi chú: bản hiện tại đặt tại
> `C:\Users\Ngo Nhat Nguyen\Desktop\Qwen window build`

---

## 2. Kiểm tra Python

Ứng dụng cần **Python 3.11 trở lên**.

1. Mở **Command Prompt** (nhấn `Win + R`, gõ `cmd`, Enter).
2. Gõ:

```bat
python --version
```

- Nếu hiện ra `Python 3.11.x` hoặc cao hơn → đã sẵn sàng, sang mục 3.
- Nếu báo `python is not recognized` → bạn cần cài Python:
  vào https://www.python.org/downloads/ tải bản mới, và **tick chọn
  “Add python.exe to PATH”** ngay ở màn hình đầu tiên của trình cài đặt.

Máy hiện tại đã có **Python 3.14.7** nên không cần cài thêm.

---

## 3. Cài đặt lần đầu (chỉ làm một lần)

1. Mở thư mục dự án.
2. **Nháy đúp vào `setup.bat`**.

Script này sẽ:

- tạo thư mục `venv` (môi trường Python riêng của ứng dụng),
- cài các thư viện cần thiết (PySide6, keyring, markdown, pygments),
- kiểm tra lại xem đã cài đủ chưa.

Khi thấy dòng **“Setup finished successfully.”** là xong.

Nếu script báo lỗi, đọc kỹ dòng `[ERROR]` để biết thiếu gì.

> Đã có sẵn `venv` trong bản này nên bạn có thể bỏ qua bước 3 và chạy ngay bước 4.

---

## 4. Khởi chạy ứng dụng

**Cách 1 — đơn giản nhất:**

Nháy đúp vào **`run.bat`** trong thư mục dự án.

**Cách 2 — bằng dòng lệnh:**

```bat
cd "C:\Users\Ngo Nhat Nguyen\Desktop\Qwen window build"
venv\Scripts\pythonw.exe main.py
```

**Cách 3 — khi cần xem log để tìm lỗi:**

```bat
venv\Scripts\python.exe main.py
```

Cách 3 hiện cửa sổ đen kèm thông báo lỗi chi tiết, hữu ích khi ứng dụng không mở được.

Nếu ứng dụng gặp lỗi khi khởi động, nó sẽ hiện một hộp thoại báo lỗi thay vì im lặng
thoát. Log của `run.bat` nằm tại `logs\app.log`.

---

## 5. Kết nối Qwen API

1. Trong cửa sổ ứng dụng, nhìn sidebar bên trái.
2. Bấm nút **“Connect Qwen API”**.
3. Cửa sổ “Connect Qwen API” hiện ra với các mục:

| Mục | Ý nghĩa |
|---|---|
| **1. Provider** | Nhà cung cấp. Hiện chỉ có Qwen. |
| **2. API key** | Ô dán API key (mặc định ẩn). Nút **Show** để hiện/ẩn. |
| **3. Endpoint and model** | Base URL, Model, và ô nhập Model ID tuỳ chỉnh. |
| **Test Connection** | Kiểm tra key và endpoint có hoạt động không. |
| **Save & Connect** | Lưu key và bắt đầu sử dụng. |
| **Connection status** | Trạng thái: Not connected / Connected / Error. |
| **Disconnect & remove stored key** | Xoá key đã lưu khỏi máy. |

4. Dán API key vào ô số 2.
5. (Tuỳ chọn) Bấm **Test Connection** để kiểm tra trước.
6. Bấm **Save & Connect**.

Sau khi lưu, sidebar hiển thị chấm xanh và dòng **“Connected”**. Bạn có thể đóng cửa sổ này.

---

## 6. Lấy API key Qwen ở đâu

API key **không** do ứng dụng này phát hành. Bạn phải tự tạo trên tài khoản
**Alibaba Cloud Model Studio (DashScope)**:

1. Đăng nhập console Alibaba Cloud Model Studio.
2. Vào trang quản lý **API-KEY**.
3. Tạo key mới và sao chép. Key thường bắt đầu bằng `sk-`.

**Chọn đúng Base URL theo tài khoản của bạn — đây là lỗi phổ biến nhất:**

| Loại tài khoản | Base URL |
|---|---|
| Trung Quốc đại lục (mặc định của app) | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| Quốc tế (Singapore) | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

Nếu bạn dùng tài khoản quốc tế mà để nguyên Base URL mặc định, `Test Connection` sẽ báo lỗi
xác thực hoặc không tìm thấy model. Hãy sửa ô Base URL trong mục số 3.

Danh sách model mặc định trong app: `qwen-turbo`, `qwen-plus`, `qwen-max`, `qwen-long`,
`qwen3-max-latest`, `qwen3-235b-a22b-instruct-cosmo`.

Tên model thay đổi theo thời gian và theo tài khoản. Nếu tên nào không dùng được, hãy
chọn **Model = Custom…** rồi tự gõ Model ID mà tài khoản của bạn có.

---

## 7. Gửi tin nhắn và nhận phản hồi

1. Gõ câu hỏi vào ô nhập ở cuối cửa sổ.
2. **Enter** để gửi, **Shift + Enter** để xuống dòng.
3. Phản hồi sẽ hiện dần theo thời gian thực (streaming).

Trong lúc chờ:

- Nút **Send** được thay bằng nút **Stop**.
- Dòng trạng thái nhỏ phía trên ô nhập hiển thị **“Thinking…”** rồi **“Streaming…”**.

Yêu cầu gửi đi gồm: **system prompt** + **các tin nhắn gần nhất của cuộc trò chuyện hiện tại**.
Số lượng tin nhắn gửi kèm được giới hạn trong **Settings → Chat preferences**.

---

## 8. Dừng phản hồi

Bấm nút **Stop** (hoặc tổ hợp `Ctrl` và đóng cửa sổ cũng sẽ huỷ).

Khi bấm Stop:

- kết nối mạng đang mở **bị đóng thật** (không chỉ ẩn vòng xoay chờ),
- phần văn bản đã nhận được **vẫn được giữ lại** trong hội thoại,
- một ghi chú “Stopped before the answer finished.” hiện dưới câu trả lời dở.

---

## 9. Quản lý hội thoại

### Tạo hội thoại mới
Bấm **`+ New chat`** trên sidebar, hoặc menu **File → New chat**, hoặc `Ctrl + N`.

### Mở hội thoại cũ
Bấm vào tên hội thoại trong danh sách sidebar. Toàn bộ tin nhắn cũ được nạp lại.

### Tìm kiếm lịch sử
Gõ vào ô **“Search title or message text…”** ở đầu sidebar.

Ô này tìm **cả trong nội dung tin nhắn**, không chỉ tiêu đề — nên bạn có thể tìm lại câu
hỏi cũ bằng một từ khoá bất kỳ đã xuất hiện trong đó. Kết quả hiện ngay trong danh sách.

### Đổi tên hội thoại
**Nháy chuột phải** vào hội thoại → **Rename…** → sửa tên → OK.

### Xoá một hội thoại
**Nháy chuột phải** vào hội thoại → **Delete…** → xác nhận **Yes**.

Hộp thoại xác nhận hiện rõ tên hội thoại trước khi xoá.

### Xoá toàn bộ lịch sử
Menu **File → Clear chat history…** → xác nhận. Thao tác này không thể hoàn tác.

### Sao lưu và phục hồi lịch sử
Menu **File → Export history…** để lưu ra một file `.json`.
Menu **File → Import history…** để nạp lại.

Import **chỉ thêm** hội thoại, **không ghi đè và không xoá** dữ liệu đang có.

---

## 10. Đổi cài đặt

Bấm **Settings** ở cuối sidebar (hoặc menu **Tools → Settings…**, hoặc `Ctrl + ,`).

| Nhóm | Nội dung |
|---|---|
| **API connection** | Base URL, thời gian timeout. Hiển thị trạng thái đã có API key chưa. |
| **Model parameters** | Model (chọn từ danh sách hoặc Custom…), Model ID tuỳ chỉnh, Temperature, Max output tokens. |
| **Appearance** | Dark/Light, cỡ chữ. |
| **Chat preferences** | Số tin nhắn cũ gửi kèm làm ngữ cảnh. |
| **System prompt** | Câu chỉ dẫn được gửi ở đầu mỗi cuộc trò chuyện mới. |
| **Data management** | Đường dẫn file lịch sử, nút Export/Import. |

Nhấn **OK** để lưu, **Cancel** để bỏ — Cancel **không** làm thay đổi cấu hình hiện tại.

Ứng dụng chặn việc lưu nếu Base URL trống hoặc thiếu `http://` / `https://`.
Nếu bạn dùng `http://` (không mã hoá), ứng dụng sẽ **cảnh báo** rằng API key của bạn
có thể bị đọc trên đường truyền.

---

## 11. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| **“No API key configured”** khi gửi tin | Chưa kết nối API | Bấm **Connect Qwen API**, dán key, **Save & Connect** |
| **“Invalid API key or access denied.”** | Key sai, hết hạn, hoặc key thuộc region khác | Kiểm tra lại key; thử đổi Base URL sang `dashscope-intl` (mục 6) |
| **“The requested model is not available…”** | Model không có trong tài khoản của bạn | Vào Settings → Model = **Custom…** → gõ Model ID đúng |
| **“Rate limit reached.”** | Gửi quá nhanh | Chờ vài giây rồi bấm **Try again** |
| **“Billing or payment issue…”** | Tài khoản hết số dư hoặc chưa bật dịch vụ | Nạp tiền / bật dịch vụ trong console Alibaba Cloud |
| **“The request timed out.”** | Mạng chậm | Bấm **Try again**, hoặc tăng **Request timeout** trong Settings |
| **“Network error.”** | Mất mạng hoặc Base URL sai | Kiểm tra mạng và lại Base URL |
| **“The server had an error.”** | Lỗi phía Qwen | Chờ rồi **Try again** |
| **Nút Stop không thấy** | Không có yêu cầu nào đang chạy | Bình thường — Stop chỉ hiện khi đang streaming |
| **Không lưu được API key** | Máy không có kho credential an toàn | Xem mục 12 |
| **Ứng dụng không mở** | Thiếu thư viện hoặc lỗi khởi động | Chạy `venv\Scripts\python.exe main.py` để xem lỗi, và đọc `logs\app.log` |

Khi một yêu cầu thất bại, phần văn bản đã nhận được **không bị mất**; ứng dụng ghi chú
rõ “Partial answer was kept in this conversation.”

---

## 12. Vị trí lưu dữ liệu

Ứng dụng lưu dữ liệu trong thư mục người dùng:

```
%USERPROFILE%\.qwen-desktop-chat\
├── chat.db         <- toàn bộ lịch sử hội thoại (SQLite)
└── settings.json   <- cấu hình (KHÔNG chứa API key)
```

Trên máy này: `C:\Users\Ngo Nhat Nguyen\.qwen-desktop-chat\`

**API key KHÔNG nằm trong hai file trên.** Key được lưu trong
**Windows Credential Manager** (Kho thông tin xác thực của Windows), dưới tên
`QwenDesktopChat`.

Kiểm tra bằng: **Control Panel → User Accounts → Credential Manager → Windows Credentials**,
tìm mục `QwenDesktopChat`.

Nếu máy không có kho credential an toàn, ứng dụng **từ chối lưu key** và báo rõ lý do,
thay vì âm thầm ghi key ra file dạng văn bản thường. Khi đó bạn vẫn dùng được ứng dụng
nhưng phải dán lại key sau mỗi lần mở.

---

## 13. Sao lưu dữ liệu

1. **Cách khuyến nghị:** dùng **File → Export history…** để xuất ra JSON.
2. **Cách sao chép toàn bộ:** đóng ứng dụng, rồi sao chép cả thư mục
   `C:\Users\Ngo Nhat Nguyen\.qwen-desktop-chat\` sang nơi an toàn.

Luôn đóng ứng dụng trước khi sao chép file `chat.db` để tránh sao chép dở dang.

---

## 14. Cập nhật ứng dụng mà không mất lịch sử

Lịch sử nằm **ngoài** thư mục dự án (trong `%USERPROFILE%\.qwen-desktop-chat\`), nên bạn
có thể thay thế toàn bộ thư mục dự án mà dữ liệu vẫn còn nguyên.

Quy trình an toàn:

1. Đóng ứng dụng.
2. Sao lưu thư mục `.qwen-desktop-chat` (mục 13).
3. Thay thế/cập nhật mã nguồn.
4. Chạy `setup.bat` nếu `requirements.txt` có thay đổi.
5. Mở lại bằng `run.bat`.

Ứng dụng **không tự xoá** lịch sử khi nâng cấp. Nếu cấu trúc database thay đổi ở phiên
bản mới, ứng dụng từ chối migrate khi không nhận ra phiên bản cũ, và giữ nguyên dữ liệu.

---

## 15. Đóng gói thành file .exe

**File `.exe` đã được build sẵn trong workspace này.** Chạy trực tiếp:

```
dist\Qwen Desktop Chat\Qwen Desktop Chat.exe
```

Nếu muốn build lại (sau khi bạn sửa code), nháy đúp **`build_exe.bat`**. Script tự cài
PyInstaller nếu thiếu, rồi tạo lại `dist\Qwen Desktop Chat\`.

Cách chạy `.exe` này:

1. Mở thư mục `dist\Qwen Desktop Chat\`.
2. Nháy đúp `Qwen Desktop Chat.exe` (không có cửa sổ console — đúng thiết kế).
3. Lần đầu mở, ứng dụng tự tạo thư mục dữ liệu `%USERPROFILE%\.qwen-desktop-chat\`.

> **Đã kiểm chứng thực tế:** `.exe` đã được build và **chạy thử thành công** — tiến trình
> sống ổn định, tự tạo `chat.db`, không có traceback, thoát sạch. Build dùng PyInstaller
> chế độ *one-folder* (`--windowed`), nên phải giữ **cả thư mục** `dist\Qwen Desktop Chat\`,
> không chỉ riêng file `.exe`.

Bản `.exe` **không** chứa API key. Key luôn nằm trong Windows Credential Manager.
Lịch sử chat cũng nằm ngoài thư mục ứng dụng, nên bạn có thể xoá và build lại thoải mái
mà không mất dữ liệu.

---

## 16. Hạn chế hiện tại

- Chỉ hỗ trợ **Qwen**. Chưa có provider khác.
- API key lưu trong Windows Credential Manager. Nếu kho này không khả dụng, key không
  được lưu và bạn phải dán lại mỗi phiên.
- Chưa hỗ trợ: đăng nhập tài khoản, đồng bộ đám mây, tải file lên, tạo ảnh, voice chat,
  tìm kiếm web, plugin.
- Công thức toán học (LaTeX) **chưa** được render — sẽ hiển thị dạng văn bản thô.
- Chỉ chạy **một** yêu cầu tại một thời điểm cho mỗi cửa sổ; nút Send bị vô hiệu khi đang chờ.
- Khi đang streaming, bạn không thể đổi hội thoại (ứng dụng chặn để tránh lẫn nội dung).

---

## 17. Những điểm đã được kiểm chứng thực tế

- Ứng dụng khởi động được: cửa sổ **“Qwen Desktop Chat”** 1280×820 hiện ra (kiểm thử
  headless).
- Bộ test tự động: **160 test pass**.
- Toàn bộ widget (sidebar, chat, dialog kết nối, dialog cài đặt) dựng được không lỗi.
- **Windows Credential Manager được nhận đúng** là kho lưu an toàn trên máy này.

- **Đóng gói `.exe`**: build thành công và **đã chạy thử** — tiến trình ổn định, tạo được
  `chat.db`, không lỗi. Xem mục 15.

**Chưa** kiểm chứng: gọi API Qwen thật (cần key thật của bạn), và giao diện hiển thị
trên màn hình thật (phiên này chạy không có màn hình).
