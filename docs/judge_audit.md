# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có (TP=24, FP=4, FN=6, TN=66) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (TP=9, FP=0, FN=21, TN=70) | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người | Xưng "em" và "nha" với khách là suồng sã; rubric phải nêu rõ xưng hô bắt buộc. |
| 2 | H-017 | PASS | FAIL | Người | "Bạn ơi" với khách lớn tuổi/tiện ích vi phạm xưng hô; thêm ví dụ "bạn" vào rubric. |
| 3 | H-029 | PASS | FAIL | Người | "Không cần nhắn thêm" là giọng ra lệnh; judge chỉ thấy lời chào mở đầu. |
| 4 | H-042 | FAIL | PASS | Người | Reply ngắn nhưng đủ kết quả và thời hạn; bỏ quy tắc bắt buộc phải xin lỗi. |
| 5 | H-051 | FAIL | PASS | Người | Từ "refund" được cho phép; bỏ rule phạt tiếng Anh khi nội dung phù hợp. |
| 6 | H-070 | PASS | FAIL | Người | Emoji không phù hợp với ngữ cảnh khiếu nại; rubric thêm cấm emoji khiếu nại. |
| 7 | H-081 | FAIL | PASS | Judge | Nhãn người sai vì reply đủ lịch sự và đầy đủ; sửa nhãn gốc. |

## Kết luận
- `tone_ok` được dùng làm metric mềm: kappa 0.757 đạt floor, precision 0.857 và recall 0.800 cũng đạt floor. Rogan-Gladen điều chỉnh tỉ lệ fail quan sát 0.280 thành 0.300.
- `helpful` bị loại khỏi gate dù precision 1.000 vì recall chỉ 0.300: 21/30 fail thật bị judge bỏ sót; kappa 0.375. Rogan-Gladen cho thấy tỉ lệ fail thật 0.300, nhưng judge chỉ quan sát được 0.090. Một gate dùng metric này sẽ bỏ qua phần lớn lỗi.
- Hành động rubric: chuẩn hoá định nghĩa xưng hô, cấm giọng ra lệnh/emoji trong khiếu nại, không bắt buộc lỗi dài dòng, và cho phép từ "refund". Sửa nhãn sai ở H-081.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
