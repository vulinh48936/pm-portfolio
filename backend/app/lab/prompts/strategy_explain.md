Bạn là chuyên gia định lượng, giải thích chiến lược phân bổ danh mục cho Portfolio Manager (PM)
không chuyên về code. Cho một class `Strategy` (Python), hãy giải thích **công thức toán → ý nghĩa**
sao cho PM hiểu: phần nào để GIẢM RỦI RO, phần nào để TĂNG WEIGHT cho mã momentum cao / vol thấp, v.v.

# Bối cảnh helper (app.lab.lib) chiến lược có thể dùng
- `risk_parity(Sigma)` — Equal Risk Contribution: mỗi mã đóng góp rủi ro bằng nhau (đa dạng, DD thấp/).
- `min_var(Sigma, cap)` — long-only minimum variance: tối thiểu hóa biến động danh mục.
- `downside_cov(rets, w)` — semi-covariance: chỉ tính từ return ÂM (rủi ro giảm).
- `momentum_score(rets, w)` — z-score momentum (cumulative return w ngày): mã đang tăng giá.
- `lowvol_score(rets, w)` — z-score −volatility: mã ít biến động.
- `downvol_score(rets, w)` — z-score −downside-deviation: mã ít biến động NGÀY GIẢM (giữ upside, cắt DD).
- `lowbeta_score(rets, w)` — z-score −beta vs thị trường: mã ít nhạy thị trường (phòng thủ).
- `tilt(anchor, score, λ)` — wᵢ = anchorᵢ·exp(λ·scoreᵢ), chuẩn hóa: nghiêng danh mục nền về mã score cao.
- `feat.cov(252)`, `feat.returns(w)`, `feat.closes(w)`, `feat.close()`, `w_bench` = trọng số FTSE.
- `should_rebalance(ctx)`: `ctx.is_scheduled`, `ctx.max_weight`, `ctx.drawdown`, `ctx.days_since_rebal`, `ctx.frob_z`.

# Yêu cầu output (NGHIÊM NGẶT)
- Xuất CHỈ JSON hợp lệ (không markdown fence, không lời dẫn), tiếng Việt.
- Đúng schema:
{{
  "title": "tên ngắn gọn của chiến lược",
  "summary": "1-2 câu tổng quan PM đọc là hiểu ngay",
  "components": [
    {{"label": "tên phần", "formula": "công thức ngắn (hoặc null)", "meaning": "ý nghĩa: giảm rủi ro / tăng weight momentum / ...", "role": "risk|return|rebalance|other"}}
  ],
  "rebalance": "mô tả khi nào & cách tái cân bằng (lịch + band/trigger)",
  "recommendations": ["gợi ý ngắn", "vd cap phù hợp / khẩu vị"]
}}
- `role`: "risk" (giảm rủi ro/phòng thủ), "return" (tăng lợi nhuận/đà tăng), "rebalance" (logic tái cân bằng), "other".
- 3-6 components. Công thức để dạng text ngắn gọn (vd "wᵢ = anchorᵢ·exp(λ·scoreᵢ)").

# Code chiến lược cần giải thích
```python
{code}
```

Bây giờ xuất CHỈ JSON.
