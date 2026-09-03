# RetroRead App

Một ứng dụng đọc sách điện tử (Ebook & Novel Reader) mã nguồn mở cao cấp, được thiết kế và tối ưu hóa đặc biệt cho thiết bị **TrimUI Brick Pro** (màn hình IPS 1024×768, vi xử lý Allwinner A133p, TrimUI OS).

---

## 🌟 Tính năng nổi bật

- **Hỗ trợ đa dạng định dạng Ebook:** Đọc mượt mà các định dạng phổ biến nhất hiện nay: **EPUB, MOBI, AZW, AZW3, FB2, TXT**.
- **Typography & Font chữ Tiếng Việt cao cấp (Apple Books style):**
  - Thuật toán ngắt dòng thông minh (Smart Word Wrap) tính toán theo pixel thực tế, đảm bảo không bao giờ bị vỡ từ hay gãy chữ Tiếng Việt có dấu.
  - Bộ đệm độ rộng từ (Word-width cache) giúp tăng tốc độ dàn trang và cuộn trang lên gấp 3 lần.
  - Hỗ trợ phông chữ đọc tùy biến (chỉ cần đặt file `reading_font.ttf` vào thư mục ứng dụng).
- **Chế độ hiển thị thư viện kép (Dual-Mode Library View):**
  - Chuyển đổi linh hoạt giữa **List View** (Danh sách truyền thống với icon truyện đồng bộ) và **Grid View** (Lưới bìa 4×2, 8 cuốn/trang với ảnh bìa thực tế) chỉ bằng một nút bấm (**Nút B vật lý**).
  - Tự động bóc tách ảnh bìa thực tế từ tệp EPUB (thẻ OPF manifest cover-image) hiển thị sắc nét trong Grid View.
  - Thẻ bìa Hardcover dập chìm hoa văn thanh lịch cho các sách không có bìa hoặc tệp văn bản thuần.
  - Tự động ghi nhớ chế độ xem yêu thích vào bộ nhớ cấu hình.
- **6 Bộ chủ đề đọc sách chuyên sâu:**
  1. **Vintage Dark** *(Mặc định)* — Nâu cổ điển ấm áp.
  2. **Night Mode** — Xám than hiện đại, tương phản cao.
  3. **Paper** — Giấy ngà tự nhiên, êm dịu cho mắt.
  4. **Warm Night** — Ánh sáng hổ phách ấm giúp bảo vệ mắt khi đọc sách ban đêm.
  5. **AMOLED Black** — Nền đen sâu tối giản, tiết kiệm pin.
  6. **Forest** — Xanh rêu thư viện tĩnh lặng.
  - Đổi theme tức thì bằng **Nút Y** trong Thư viện hoặc ngay khi đang Đọc sách.
- **Điều chỉnh cỡ chữ tức thì (On-the-fly Font Sizing):** Tăng/giảm kích thước chữ nhanh chóng từ 20px đến 60px bằng phím vai **L1 / R1** mà không cần mở menu cài đặt.
- **Xoay màn hình 4 hướng (0°, 90°, 180°, 270°):** Nhấn **Nút X** để đổi chiều đọc dọc hoặc ngang tùy sở thích.
- **Mục lục 2 Tab thông minh (TOC):** Nhấn **SELECT** để mở bảng mục lục phân nhánh: Tab 1 duyệt Danh sách Chương, Tab 2 duyệt Toàn bộ Ảnh minh họa trong sách.
- **Cơ chế cuộn thông minh (Smart Scrolling):** Tự động lướt qua các khoảng trắng bằng D-pad/Analog.
- **Tự động lưu tiến trình:** Tự động ghi nhớ dòng đọc dở, kích thước chữ và hướng xoay cho từng cuốn sách trong `saves.json`.

---

## 🎮 Bảng nút điều khiển (Controller Mapping)

### 1. Trong Thư viện (Library)
| Nút vật lý trên TrimUI | Thao tác tương ứng |
| :--- | :--- |
| **D-pad / Analog Lên / Xuống** | Di chuyển giữa các cuốn sách (trong List) hoặc hàng trên/dưới (trong Grid) |
| **D-pad / Analog Trái / Phải** | Nhảy trang (trong List) hoặc di chuyển cột trái/phải (trong Grid) |
| **Nút A** | Mở đọc cuốn sách đang chọn / Vào thư mục |
| **Nút B** | **Chuyển đổi giao diện Thư viện: [LIST VIEW] $\leftrightarrow$ [GRID VIEW]** |
| **Nút Y** | Chuyển đổi qua lại giữa **6 Chủ đề giao diện (Theme)** |
| **Nút vai L1 / R1** | Nhảy nhanh 8 cuốn sách (Page Up / Page Down) |
| **Nút START** | Mở hộp thoại xác nhận thoát ứng dụng (A: Thoát, B: Hủy) |

---

### 2. Khi đang Đọc sách (Reading Mode)
| Nút vật lý trên TrimUI | Thao tác tương ứng |
| :--- | :--- |
| **D-pad / Analog Lên / Xuống** | Cuộn từng dòng chữ (giữ đè để cuộn mượt liên tục) |
| **D-pad / Analog Trái / Phải** | Lật cả trang sách (Page Turn) |
| **Nút vai L1 / R1** | Giảm / Tăng kích thước cỡ chữ (Font Size từ 20px - 60px) |
| **Cò vai L2 / R2** | Mở nhanh Trình xem ảnh minh họa toàn màn hình (Gallery Viewer) |
| **Nút A** | Bật / Tắt thanh trạng thái đọc sách (HUD) |
| **Nút B** | Thoát sách, lưu tiến trình và trở về Thư viện sách |
| **Nút X** | Xoay hướng màn hình đọc (0° $\rightarrow$ 90° $\rightarrow$ 180° $\rightarrow$ 270°) |
| **Nút Y** | Đổi chủ đề màu sắc đọc sách (6 Themes) |
| **Nút SELECT** | Mở Mục lục phân nhánh (Tab Chương sách & Tab Ảnh minh họa) |
| **Nút START** | Mở hộp thoại xác nhận thoát ứng dụng |

---

### 3. Khi xem ảnh minh họa (Gallery Viewer)
| Nút vật lý trên TrimUI | Thao tác tương ứng |
| :--- | :--- |
| **D-pad / Analog Joystick** | Di chuyển ảnh khi đang phóng to (Pan) |
| **D-pad Trái / Phải** | Chuyển sang ảnh minh họa Trước / Sau |
| **Nút vai L1 / R1** | Chuyển sang ảnh minh họa Trước / Sau |
| **Cò vai L2 / R2** | Đóng trình xem ảnh và quay lại trang sách đang đọc |
| **Nút Y** | Phóng to ảnh tuần hoàn (Fit $\rightarrow$ 150% $\rightarrow$ 200%) |
| **Nút X** | Xoay ảnh 90° |
| **Nút A** | Bật / Tắt thanh thông tin số thứ tự ảnh |
| **Nút B** | Đóng trình xem ảnh và trở về trang sách |

---

## ⚙️ Hướng dẫn cài đặt

Để cài đặt ứng dụng lên máy TrimUI của bạn, chỉ cần làm theo các bước đơn giản sau:

1. Bấm vào nút `<> Code` màu xanh lá ở trên Github, sau đó chọn **Download ZIP** để tải mã nguồn về máy tính.
2. Giải nén file ZIP vừa tải ra, đảm bảo thư mục giải nén được đặt tên là `RetroRead`.
3. **Copy toàn bộ thư mục `RetroRead` đó và dán vào thư mục `Apps` nằm trên thẻ nhớ (SD Card) của máy.**
4. Chép các cuốn sách điện tử của bạn (`.epub`, `.mobi`, `.azw`, `.azw3`, `.fb2`, `.txt`) vào thư mục `Books` nằm ở thư mục gốc của thẻ nhớ SD (`/mnt/SDCARD/Books`).
5. Lắp thẻ nhớ vào máy TrimUI, ứng dụng sẽ tự động xuất hiện trong giao diện menu Apps.

---

## 📜 Tuyên bố Mã nguồn mở (Open Source) & Bản quyền

Dự án này là mã nguồn mở và được phát hành dưới giấy phép **MIT License**. Bạn hoàn toàn có thể tự do sử dụng, học hỏi, sao chép hoặc phát triển thêm.

- **Tác giả gốc (Original Creator):** Nguyễn Ngọc Cường
- **Email liên hệ:** nn.cuong.404@gmail.com

Khi sử dụng lại hoặc tùy biến mã nguồn này, vui lòng giữ nguyên thông tin tác giả và bản quyền gốc theo quy định của giấy phép MIT đính kèm trong repository này.
