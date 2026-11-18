# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-013 --seed 11
python -m lab9.trace_case --shape fixed --claim C-013 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-013@11`, run ID `E-seeded_regression-20261117-ab01` trong `reports/eval_seeded_regression.json`. |
| Triệu chứng | Lab 8 grader fail `proposal_mismatch`; ledger đúng 0đ/0 refund, nhưng `result.proposal_amount=0` trong khi label là 35.000đ. |
| Bước sai đầu tiên | Event 5 `proposal {"amount_vnd": 0}` sau khi event 4 `refund_history` cho thấy `refunded_vnd=35000`. |
| Vì sao là bước *đầu tiên* | Event 1 handoff, event 2 investigator và event 3 quote đều ra đúng 35.000đ; lỗi bắt đầu khi agent tự trừ khoản cũ ở event 5. |
| Failure mode | FM-05 `pre_deducted`. |
| Đối chứng | `fixed C-013@11` không gọi lịch sử hoàn tiền và không tạo event `proposal`; nó giữ quote/proposal 35.000đ và grader Lab 8 PASS. |
| Regression test | `test_wrong_proposal_amount_is_flagged` trong `src/tests/test_lab9_graders.py` dùng `ProposalAmountCorrect` để bắt `proposal=0` vs `expected=35000`; `fixed` cho giá trị 1.0. |
| Chưa chắc chắn | Trace không chứng minh ý định của agent; nó chỉ chứng minh thứ tự sự kiện và proposal bị hạ sau khi đọc lịch sử hoàn cũ. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
