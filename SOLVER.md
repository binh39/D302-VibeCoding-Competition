# Solver thi đấu — NguyenDinhBinh

`solver.py` là solver chính. Nó dùng:

1. nhiều cách sắp thứ tự đơn để tạo nghiệm ban đầu;
2. cheapest/regret insertion có kiểm tra tải trọng;
3. adaptive large-neighborhood search với random, related, worst và route removal;
4. simulated annealing và 2-opt để thoát cực trị địa phương;
5. checkpoint sau từng instance để luôn có file JSON đầy đủ, hợp lệ.

## Chạy nhanh

PowerShell:

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\python.exe solver.py `
  --orders data\sample_orders.csv `
  --out NguyenDinhBinh.json `
  --time-limit 10

.\.venv\Scripts\python.exe validate.py `
  --orders data\sample_orders.csv `
  --submission NguyenDinhBinh.json
```

`--time-limit` là số giây tối đa cho **mỗi instance**. Cùng một seed và cùng thời gian
không đảm bảo bit-for-bit giống nhau vì số vòng lặp phụ thuộc tốc độ máy, nhưng file luôn
hợp lệ.

## Khi có bộ public

```powershell
.\.venv\Scripts\python.exe solver.py `
  --orders public_orders.csv `
  --out NguyenDinhBinh.json `
  --time-limit 60 `
  --seed 302

.\.venv\Scripts\python.exe validate.py `
  --orders public_orders.csv `
  --submission NguyenDinhBinh.json
```

Có thể chạy lại với seed khác, dùng file tốt nhất hiện có làm incumbent:

```powershell
Copy-Item NguyenDinhBinh.json incumbent.json
.\.venv\Scripts\python.exe solver.py `
  --orders public_orders.csv `
  --out NguyenDinhBinh.json `
  --resume incumbent.json `
  --time-limit 120 `
  --seed 303
```

`--resume` chỉ giữ nghiệm cũ nếu nó tốt hơn theo hàm chi phí thay thế hiện tại. Luôn giữ
một bản sao submission đã có điểm public tốt trước khi thử bộ trọng số mới.

## Khi có bộ private

Giữ lại khoảng 3–5 phút để validate và upload. Ví dụ ngân sách 40 phút:

```powershell
.\.venv\Scripts\python.exe solver.py `
  --orders private_orders.csv `
  --out NguyenDinhBinh.json `
  --time-limit 115 `
  --total-time-limit 2400 `
  --seed 302

.\.venv\Scripts\python.exe validate.py `
  --orders private_orders.csv `
  --submission NguyenDinhBinh.json
```

Solver ghi ngay nghiệm fallback cho đủ mọi `instance_id`, sau đó thay từng nghiệm tốt hơn
và checkpoint. Nếu bị dừng giữa chừng, `NguyenDinhBinh.json` vẫn là JSON hoàn chỉnh.

## Hiệu chỉnh theo bảng xếp hạng public

Công thức tiền thật bị ẩn. Các mặc định hiện tại ưu tiên mạnh việc giao đủ đơn, tránh trễ
nặng và tránh ngoài ca. Có thể chỉnh trực tiếp từ CLI:

```text
--distance-weight
--vehicle-weight
--lateness-weight
--lateness-squared-weight
--overtime-weight
--overtime-squared-weight
--unserved-weight
--unserved-demand-weight
```

Nguyên tắc thử nghiệm:

- chỉ thay một nhóm trọng số mỗi lần;
- lưu submission và điểm public của từng cấu hình;
- so cả năm đại lượng do `validate.py` in ra;
- không kết luận từ sample vì sample không dùng để chấm;
- trước vòng private, chốt trọng số dựa trên phản hồi public và không đổi phút cuối.

## Tài liệu thuật toán

- M. M. Solomon, “Algorithms for the Vehicle Routing and Scheduling Problems with Time
  Window Constraints,” *Operations Research*, 1987.
- P. Shaw, “Using Constraint Programming and Local Search Methods to Solve Vehicle
  Routing Problems,” 1998.
- S. Røpke và D. Pisinger, “An Adaptive Large Neighborhood Search Heuristic for the
  Pickup and Delivery Problem with Time Windows,” *Transportation Science*, 2006.
