# SwiftRoute — Cuộc thi tối ưu giao hàng

Bạn có một kho hàng, một đội xe tải, và vài trăm đơn cần giao trong ngày. Việc của bạn:
viết code quyết định **xe nào đi đâu, theo thứ tự nào**, sao cho **tổng chi phí vận hành**
thấp nhất.

Chi phí vận hành liên quan tới năm thứ: tổng quãng đường các xe chạy, số xe phải huy
động, mức độ trễ hẹn với khách, thời gian tài xế làm ngoài ca, và những đơn cuối cùng
không giao được.

Bạn sẽ không tìm được lời giải tối ưu — bài toán này không ai giải tối ưu được ở quy mô
đó. Mục tiêu là **tốt hơn các đội khác**.

## Bắt đầu trong 2 phút

Cần Python 3.10 trở lên. Không phải cài thư viện gì cả.

```bash
git clone https://github.com/VinUni-AI20k/D302-VibeCoding-Competition.git
cd D302-VibeCoding-Competition

python starter/solver_starter.py --orders data/sample_orders.csv --out TEN_DOI.json --team TEN_DOI
python validate.py --orders data/sample_orders.csv --submission TEN_DOI.json
```

Chạy được là môi trường của bạn ổn. Lời giải mẫu rất tệ — đó là chủ ý, nó chỉ để chứng
minh đường ống thông suốt.

## Đọc theo thứ tự này

| File | Nội dung |
|---|---|
| **[GUIDE.md](GUIDE.md)** | **Bắt đầu ở đây.** Hướng dẫn từng bước, có code cụ thể |
| [PROBLEM.md](PROBLEM.md) | Đề bài chính thức. Luật cứng, luật mềm, chi phí vận hành |
| [DATA_FORMAT.md](DATA_FORMAT.md) | Định dạng CSV đề bài và JSON nộp bài |
| [SCORING.md](SCORING.md) | Cách tính điểm |
| [RULES.md](RULES.md) | Thể lệ, mốc thời gian, cách nộp |

## Trong repo có gì

```
GUIDE.md                    hướng dẫn từng bước
PROBLEM.md  DATA_FORMAT.md  SCORING.md  RULES.md
validate.py                 kiểm tra lời giải trước khi nộp
starter/solver_starter.py   lời giải mẫu ngây thơ, thay bằng code của bạn
swiftroute/                 thư viện đọc đề và đo lời giải
data/sample_orders.csv      3 bài nhỏ để bạn chạy thử
tests/                      chạy `pytest` để chắc chắn môi trường ổn
```

**Lưu ý:** `data/sample_orders.csv` chỉ là bài mẫu để chạy thử. Đề thi thật (bộ public và
bộ private) sẽ được ban tổ chức phát riêng trên Discord theo lịch trong
[RULES.md](RULES.md).

## Ba điều nên biết ngay

**Bạn được phép bỏ đơn.** Đơn nào không nằm trong tuyến nào thì coi như không giao. Bị
phạt, nhưng hợp lệ — và đôi khi là lựa chọn đúng. Rất nhiều đội thua vì cố giao bằng
được mọi đơn.

**Có năm thứ bị đo, không phải một.** Tổng quãng đường, số xe dùng, mức trễ hẹn, thời
gian làm ngoài ca, và các đơn bị bỏ. Chỉ tối ưu quãng đường là thua.

**Chờ cũng mất thời gian.** Ghé một khách sớm hơn `ready_time` thì xe phải đứng đợi, và
mọi khách phía sau trong tuyến bị đẩy lùi theo.

Chúc vui. Bắt đầu ở [GUIDE.md](GUIDE.md).

## Solver của đội NguyenDinhBinh

Solver thi đấu nằm ở `solver.py`; cách chạy public/private, resume, ngân sách thời gian và
hiệu chỉnh trọng số nằm trong [SOLVER.md](SOLVER.md). `starter/solver_starter.py` được giữ
lại làm baseline để so sánh.
