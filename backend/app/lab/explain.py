"""Explain a strategy to the PM: formula, then what it means.

Presets use curated text, which is exact and needs no LLM. Generated or hand-written
code goes to the LLM (temperature 0) and the result is cached.

Schema:
  {title, summary, components:[{label, formula, meaning, role}], rebalance, recommendations}
  role is one of risk, return, rebalance, other; the frontend colours by it.

The explanation text itself stays in Vietnamese: the PM reads it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.lab.config import LabConfig


def _c(label: str, formula: str | None, meaning: str, role: str) -> dict:
    return {"label": label, "formula": formula, "meaning": meaning, "role": role}


# Blocks reused across presets
_ERC = _c(
    "Equal Risk Contribution (ERC) trên covariance",
    "Σ = cov(returns, 252) (Ledoit-Wolf, năm hóa);  chọn w sao cho wᵢ·(Σw)ᵢ = const ∀i",
    "Mỗi mã đóng góp RỦI RO bằng nhau: mã biến động mạnh → weight nhỏ, mã ổn định → weight lớn. "
    "Tự nhiên đa dạng hóa, không để 1 mã thống trị → drawdown thấp hơn.",
    "risk",
)
_TILT = _c(
    "Tilt nhân (multiplicative)",
    "wᵢ = anchorᵢ · exp(λ · scoreᵢ),  rồi chuẩn hóa Σw=1 (long-only)",
    "Nghiêng danh mục nền (anchor) về phía mã có score cao. λ càng lớn càng lệch mạnh. "
    "Dùng exp nên không tạo weight âm.",
    "return",
)
_MOM = _c(
    "Momentum score",
    "momᵢ = z( Π(1+rᵢ, 120 ngày) − 1 )   (z = chuẩn hóa cross-sectional)",
    "Ưu tiên mã có đà tăng giá 120 ngày (≈6 tháng) — 'mã đang khỏe được tăng weight'.",
    "return",
)
_DOWNVOL = _c(
    "Low downside-vol score",
    "downvolᵢ = z( −√( mean( min(rᵢ,0)² , 120 ngày ) ) )",
    "Ưu tiên mã có ÍT biến động NGÀY GIẢM (semi-deviation). Chỉ phạt rủi ro giảm, KHÔNG phạt biến "
    "động tăng → giữ được upside, cắt drawdown. 'Tăng weight cho mã tăng ổn định'.",
    "risk",
)
_LOWVOL = _c(
    "Low-vol score",
    "lowvolᵢ = z( −std(rᵢ, 60 ngày) )",
    "Ưu tiên mã biến động tổng thấp 60 ngày → thiên về mã ổn định, giảm rủi ro danh mục.",
    "risk",
)
_ER_MOM = _c(
    "Kaufman ER-momentum score",
    "ERᵢ = |giáᵢ(t)−giáᵢ(t−20)| / Σ|Δgiá từng phiên, 20 ngày| ∈[0,1];  "
    "er_momᵢ = z( momᵢ · (0.5 + 0.5·ERᵢ) )",
    "Momentum THÔ (120 ngày) được nhân trọng số theo Kaufman Efficiency Ratio — 'độ sạch' của "
    "xu hướng: mã đi lên MƯỢT (ER≈1) giữ full momentum, mã tăng nhờ vài phiên GIẬT CỤC/nhiễu "
    "(ER thấp) bị chiết khấu về 50%. Lọc bớt momentum 'ảo' do nhiễu. Cửa sổ ER mặc định là 20 phiên "
    "(theo Kaufman gốc, thiên về cửa sổ ngắn).",
    "return",
)
_CAP = _c(
    "Trần weight/mã (cap)",
    "wᵢ ≤ cap; phần vượt phân bổ lại cho mã chưa chạm trần (waterfall)",
    "Chặn tập trung quá mức vào 1 mã — kiểm soát rủi ro đơn lẻ.",
    "risk",
)


# Curated explanations per preset
PRESET_EXPLANATIONS: dict[str, dict] = {
    "risk_parity": {
        "title": "Risk Parity (Equal Risk Contribution)",
        "summary": "Phân bổ sao cho mỗi mã gánh rủi ro bằng nhau — danh mục đa dạng, cân bằng rủi ro.",
        "components": [_ERC],
        "rebalance": "Hàng quý, no-trade band 1.5%.",
        "recommendations": ["Phù hợp khẩu vị cân bằng/đa dạng", "Cap ~25%"],
    },
    "risk_parity_monthly": {
        "title": "Risk Parity hàng tháng (Equal Risk Contribution)",
        "summary": "Như Risk Parity (mỗi mã gánh rủi ro bằng nhau) nhưng tái cân bằng hàng tháng — "
                   "bám phân bổ rủi ro sát hơn, đổi lại turnover/phí cao hơn bản hàng quý.",
        "components": [_ERC],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Bám rủi ro sát hơn risk_parity quý", "Turnover cao hơn → cân nhắc phí", "Cap ~25%"],
    },
    "risk_parity_dd": {
        "title": "Risk Parity + Drawdown Gate",
        "summary": "Như Risk Parity nhưng chỉ tái cân bằng khi danh mục đang lỗ sâu — giảm giao dịch thừa.",
        "components": [
            _ERC,
            _c("Drawdown gate (gate A)",
               "tại kỳ rebalance: chỉ giao dịch nếu drawdown < −8%; ép giao dịch nếu max weight > 25%",
               "Chỉ tái cân bằng khi đang drawdown (cần chỉnh) hoặc khi 1 mã phình quá trần — "
               "tránh giao dịch khi danh mục đang ổn → tiết kiệm phí.",
               "rebalance"),
        ],
        "rebalance": "Hàng quý NHƯNG có điều kiện: chỉ rebalance khi drawdown < −8% (hoặc max weight > 25%).",
        "recommendations": ["Giảm turnover so với risk_parity thuần", "Cap ~25%"],
    },
    "min_var": {
        "title": "Minimum Variance (long-only)",
        "summary": "Tìm danh mục có phương sai (biến động) nhỏ nhất — phòng thủ tối đa.",
        "components": [
            _c("Minimum variance",
               "min wᵀΣw  s.t. Σw=1, 0≤wᵢ≤cap   (SLSQP)",
               "Tối thiểu hóa biến động tổng của danh mục → dồn về nhóm mã ít rủi ro + ít tương quan. "
               "Drawdown nhỏ nhưng có thể bỏ lỡ mã tăng mạnh.",
               "risk"),
            _CAP,
        ],
        "rebalance": "Hàng quý, no-trade band 1.5%.",
        "recommendations": ["Phòng thủ", "Cap 25%"],
    },
    "factor_tilt": {
        "title": "Factor Tilt (Momentum + Low-vol) trên FTSE",
        "summary": "Bám sát rổ FTSE rồi nghiêng nhẹ về mã momentum cao + vol thấp.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench (trọng số FTSE tại thời điểm t)",
               "Lấy rổ FTSE làm nền → giữ tracking error thấp, không lệch quá xa benchmark.", "other"),
            _MOM, _LOWVOL,
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(1.0 · (0.5·mom + 0.5·lowvol)ᵢ)"},
        ],
        "rebalance": "Hàng quý, no-trade band 1.5%.",
        "recommendations": ["Gần benchmark", "λ=1.0 (tilt nhẹ)"],
    },
    "mom_downvol_tilt": {
        "title": "Momentum + Downside-Vol Tilt trên FTSE",
        "summary": "Nghiêng rổ FTSE về mã momentum cao + ít rủi ro GIẢM.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE.", "other"),
            _MOM, _DOWNVOL,
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(2.5 · (0.5·mom + 0.5·downvol)ᵢ)"},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Tilt mạnh (λ=2.5) trên nền FTSE", "KHUYẾN NGHỊ cap 35%"],
    },
    "erc_mom_tilt_monthly": {
        "title": "ERC + Momentum/Low-vol Tilt (hàng tháng)",
        "summary": "Nền Equal-Risk (đa dạng) rồi nghiêng nhẹ momentum + low-vol. Thiên về phòng thủ. Rebalance hàng tháng.",
        "components": [
            _ERC, _MOM, _LOWVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · (0.5·mom + 0.5·lowvol)ᵢ)"},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Thiên phòng thủ (nền ERC + low-vol)", "KHUYẾN NGHỊ cap 25%"],
    },
    "erc_mom_tilt_quarterly": {
        "title": "ERC + Momentum/Low-vol Tilt (hàng quý)",
        "summary": "Y hệt bản hàng tháng (nền ERC nghiêng momentum + low-vol) nhưng rebalance hàng quý — turnover/phí thấp hơn, bám tín hiệu chậm hơn.",
        "components": [
            _ERC, _MOM, _LOWVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · (0.5·mom + 0.5·lowvol)ᵢ)"},
        ],
        "rebalance": "Hàng quý, no-trade band 1.5%.",
        "recommendations": ["Turnover/phí thấp hơn bản tháng", "Bám tín hiệu chậm hơn → so sánh với bản tháng", "KHUYẾN NGHỊ cap 25%"],
    },
    "erc_mom_trail": {
        "title": "ERC + Momentum/Low-vol Tilt + Trailing-Loss Gate (hàng tháng)",
        "summary": "Như erc_mom_tilt_monthly (nền ERC nghiêng momentum + low-vol) NHƯNG thêm STOP-LOSS "
                   "ĐỘNG per-stock: mã nào rớt > 15% so với đỉnh 60 ngày gần nhất thì CẮT HẲN tỉ trọng "
                   "(×0), chia lại cho mã khỏe. LƯU Ý: cửa sổ đỉnh mặc định là 60 ngày — cân nhắc "
                   "TRAIL_WIN=120 nếu muốn bắt downtrend kéo dài thay vì phản ứng nhanh.",
        "components": [
            _ERC, _MOM, _LOWVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · (0.5·mom + 0.5·lowvol)ᵢ)"},
            _c("⭐ Trailing-loss gate per-stock (stop-loss động)",
               "trail_ddᵢ = giáᵢ(t-1) / max(giáᵢ, 60 ngày) − 1;  nếu trail_ddᵢ ≤ −15% → wᵢ ×= 0 (cắt hẳn), "
               "rồi chuẩn hóa Σw=1",
               "Mã đang lao dốc > 15% từ đỉnh 60-ngày bị loại khỏi danh mục, vốn dồn sang mã còn khỏe → "
               "né tiếp tục thua lỗ + cắt drawdown. Đánh giá mỗi kỳ rebalance (tháng). Thiết kế cắt SỚM "
               "(ngưỡng 15%) và cắt HẲN (×0) thay vì cắt nửa vời. Cửa sổ đỉnh dài (120) bắt downtrend kéo "
               "dài, cửa sổ ngắn (60) phản ứng nhanh hơn. No-look-ahead.", "risk"),
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%; trailing-stop đánh giá mỗi kỳ.",
        "recommendations": ["Thêm tầng stop-loss động so với erc_mom thuần; chỉnh TRAIL_WIN để đổi giữa phản ứng nhanh và bắt downtrend dài",
                            "⚠️ Họ ERC underweight VIC → dòng PHÒNG THỦ, không hợp mục tiêu bám sát index",
                            "Muốn cắt drawdown sâu hơn: kết hợp cash overlay (đặt regime_floor=0.0)",
                            "Chỉnh độ chặt qua TRAIL_X / TRAIL_WIN / TRAIL_RED", "KHUYẾN NGHỊ cap 25-30%"],
    },
    "semi_erc_mom_trail": {
        "title": "Semi-ERC + Momentum/DownVol Tilt + Trailing-Loss Gate (hàng tháng)",
        "summary": "Như semi_erc_mom_monthly (nền ERC trên semi-covariance nghiêng momentum + downside-vol) "
                   "+ STOP-LOSS ĐỘNG per-stock: mã rớt > 15% từ đỉnh 60 ngày → cắt hẳn tỉ trọng, chia lại. "
                   "Phòng thủ KÉP (semi-cov + trailing-stop). LƯU Ý: cửa sổ đỉnh mặc định là 60 ngày — "
                   "cân nhắc TRAIL_WIN=120 nếu muốn bắt downtrend kéo dài.",
        "components": [
            _ERC, _MOM, _DOWNVOL,
            {**_TILT, "formula": "wᵢ = baseᵢ · exp(2.0 · (0.5·mom + 0.5·downvol)ᵢ),  base = ERC trên semi-cov"},
            _c("⭐ Trailing-loss gate per-stock (stop-loss động)",
               "trail_ddᵢ = giáᵢ(t-1) / max(giáᵢ, 60 ngày) − 1;  nếu ≤ −15% → wᵢ ×= 0, rồi chuẩn hóa",
               "Mã lao dốc > 15% từ đỉnh 60-ngày bị loại, vốn dồn sang mã khỏe → cắt drawdown. Thiết kế cắt "
               "sớm và cắt hẳn. Cửa sổ đỉnh dài (120) bắt downtrend kéo dài, ngắn (60) phản ứng nhanh. No-look-ahead.", "risk"),
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%; trailing-stop đánh giá mỗi kỳ.",
        "recommendations": ["Thêm tầng stop-loss động so với semi_erc thuần; chỉnh TRAIL_WIN theo nhịp muốn bắt",
                            "⚠️ Underweight VIC → dòng PHÒNG THỦ",
                            "Muốn cắt drawdown sâu hơn: + cash overlay (regime_floor=0.0)",
                            "KHUYẾN NGHỊ cap 30%"],
    },
    "semi_erc_mom_liqshare": {
        "title": "Semi-ERC + Momentum/DownVol + Trailing-Gate, THANH KHOẢN-NATIVE (liq-share cap)",
        "summary": "semi_erc_mom_trail bản tự xử lý thanh khoản Ở TẦNG WEIGHT, không cần biết AUM: "
                   "(1) trần weight mỗi mã theo TỈ TRỌNG thanh khoản capᵢ = 7·ADTVᵢ/ΣADTV → weight ∝ ADTV "
                   "→ trade ∝ ADTV → spill-days ĐỀU nhau mọi mã ở MỌI AUM; (2) score nghiêng 15% về mã dễ "
                   "trade; (3) tự khai ADTV floor 5 tỷ — engine loại cả mã passive (APH).",
        "components": [
            _ERC, _MOM, _DOWNVOL,
            {**_TILT, "formula": "score = 0.85·(0.5·mom + 0.5·downvol) + 0.15·z(log ADTV);  wᵢ = baseᵢ·exp(2·scoreᵢ)"},
            _c("Trailing-loss gate per-stock (stop-loss động)",
               "trail_ddᵢ = giáᵢ(t-1) / max(giáᵢ, 60 ngày) − 1;  nếu ≤ −15% → wᵢ ×= 0",
               "Mã lao dốc > 15% từ đỉnh 60-ngày bị loại, vốn dồn sang mã khỏe → cắt drawdown.", "risk"),
            _c("⭐ Liquidity-share cap (trần weight theo tỉ trọng thanh khoản)",
               "capᵢ = max(0.5%, 7 · ADTVᵢ / ΣADTV);  Σcap(mã sống) < 1 → scale caps tỉ lệ",
               "Weight mã illiquid bị chặn CẤU TRÚC → lệnh rebalance ∝ thanh khoản của chính mã → "
               "spill-days đều nhau mọi mã ở MỌI AUM, không mã nào là nút thắt. Không cần nhập AUM. "
               "Feasibility-scaling chống dồn cục khi trailing gate cắt gần hết rổ lúc bear.", "risk"),
            _c("⭐ ADTV floor tự khai (adtv_floor_bn = 5)",
               "wᵢ = 0 nếu ADTVᵢ < 5 tỷ/phiên (engine áp TOÀN vector, gồm mã passive)",
               "Diệt 'landmine' thanh khoản như APH (0.76 tỷ, giữ passive theo benchmark mà allocate "
               "không thấy) — không cần user cấu hình.", "risk"),
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Như semi_erc_mom_trail nhưng tự xử lý thanh khoản ở tầng weight — KHÔNG cần nhập AUM",
                            "LAM nhỏ hơn (5-6) chặn thanh khoản chặt hơn nhưng bó weight nhiều hơn; mặc định 7",
                            "⚠️ Vẫn thuộc họ ERC underweight VIC. Cap 30%"],
    },
    "erc_mom_er": {
        "title": "ERC + Kaufman ER-Momentum/Low-vol Tilt (hàng tháng)",
        "summary": "Như erc_mom_tilt_monthly (nền ERC nghiêng momentum + low-vol) NHƯNG thay momentum THÔ "
                   "bằng KAUFMAN EFFICIENCY RATIO momentum: momentum được nhân trọng số theo 'độ sạch' của "
                   "xu hướng (mã trend mượt giữ full, mã tăng giật cục bị chiết khấu). Lọc momentum 'ảo'. ",
        "components": [
            _ERC, _ER_MOM, _LOWVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · (0.5·er_mom + 0.5·lowvol)ᵢ)"},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Khác erc_mom thuần ở chỗ lọc momentum theo độ mượt của xu hướng (Kaufman ER)",
                            "ER_WIN=20 theo Kaufman gốc (cửa sổ ngắn); chỉnh qua ER_WIN/MOM_WIN",
                            "⚠️ Vẫn họ ERC underweight VIC → dòng phòng thủ; KHUYẾN NGHỊ cap 25-30%"],
    },
    "erc_mom_er_v2": {
        "title": "ERC + Momentum chất lượng (Kaufman ER) — danh mục đa dạng, hàng tháng",
        "summary": "Danh mục cân bằng rủi ro (ERC) nghiêng nhẹ về các mã có XU HƯỚNG TĂNG MƯỢT: momentum "
                   "150 phiên được nhân với Kaufman Efficiency Ratio (độ 'mượt' của đường giá) để lọc bỏ "
                   "momentum ảo do vài phiên giật cục, cộng thêm điểm cho mã biến động thấp. Danh mục rộng "
                   "~15 mã, tự đa dạng hóa.",
        "components": [
            _ERC,
            {**_ER_MOM, "formula": "ERᵢ = |giáᵢ(t)−giáᵢ(t−20)| / Σ|Δgiá từng phiên, 20 ngày| ∈[0,1];  "
                                   "er_momᵢ = z( momᵢ(150 phiên) · ERᵢ )",
             "meaning": "Momentum 150 phiên nhân với độ mượt ER: mã tăng ĐỀU ĐẶN giữ nguyên điểm; mã tăng "
                        "nhờ vài phiên giật cục/nhiễu bị triệt gần hết. Chỉ 'cưỡi' xu hướng có chất lượng — "
                        "đây là nguồn return chính của chiến lược."},
            _LOWVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · (0.7·er_mom + 0.3·lowvol)ᵢ)",
             "meaning": "Nghiêng danh mục nền ERC về mã điểm cao. Hệ số 2.0 là mức NHẸ có chủ đích: giữ "
                        "danh mục rộng, rủi ro vẫn cân bằng — không dồn vào vài mã."},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Hợp với mandate danh mục đa dạng kiểu quỹ (~15 mã ≥1%); muốn bản tấn công cô đặc hơn → xem mom_er_liqshare",
                            "Chỉnh độ nghiêng qua W_MOM (momentum vs low-vol) và LAM (độ mạnh tilt)",
                            "⚠️ Cửa sổ ER=20 là tham số nhạy — kỳ vọng thực tế nên thấp hơn backtest. Cap khuyến nghị 25%"],
    },
    "erc_mom_er_v3": {
        "title": "ERC + Momentum chất lượng, CÓ CHẶN BIÊN ĐỘ NGHIÊNG — hàng tháng",
        "summary": "Danh mục cân bằng rủi ro (ERC) nghiêng về các mã có XU HƯỚNG TĂNG MƯỢT (momentum 150 "
                   "phiên nhân Kaufman Efficiency Ratio để lọc momentum ảo, cộng điểm ổn định giá), với "
                   "một bước KẸP ĐIỂM: điểm số bị giới hạn trong [−1, +1] trước khi nghiêng. Bước nghiêng "
                   "là hàm mũ và rổ chỉ ~20 mã, nên nếu không kẹp thì một mã điểm cực đoan có thể bị đẩy "
                   "thẳng lên trần cap 25% và chính trần cứng — chứ không phải mô hình — định đoạt tỉ "
                   "trọng. Kẹp điểm trả quyền quyết định tỉ trọng về cho mô hình, đồng thời hạ mức nhảy "
                   "tỉ trọng giữa 2 kỳ.",
        "components": [
            _ERC,
            {**_ER_MOM, "formula": "ERᵢ = |giáᵢ(t)−giáᵢ(t−20)| / Σ|Δgiá từng phiên, 20 ngày| ∈[0,1];  "
                                   "er_momᵢ = z( momᵢ(150 phiên) · ERᵢ )",
             "meaning": "Momentum 150 phiên nhân với độ mượt ER: mã tăng ĐỀU ĐẶN giữ nguyên điểm; mã tăng "
                        "nhờ vài phiên giật cục/nhiễu bị triệt gần hết. Nguồn return chính của chiến lược."},
            _LOWVOL,
            _c("⭐ Kẹp điểm số trước khi tilt (SCORE_CAP = 1.0)",
               "scoreᵢ ← clip(scoreᵢ, −1.0, +1.0)  — áp SAU khi cộng 0.7·er_mom + 0.3·lowvol",
               "Đóng khung chênh lệch hệ số nghiêng giữa mã cao điểm nhất và thấp điểm nhất ở "
               "exp(2·λ·SCORE_CAP), thay vì để đuôi phân phối cross-sectional tự quyết — nhờ đó một mã "
               "điểm cực đoan không bị đẩy weight lên sát trần cap. SCORE_CAP là núm vặn: hạ xuống → biên "
               "độ nghiêng hẹp hơn, danh mục ổn định/đa dạng hơn; nới lên → nghiêng mạnh hơn.",
               "risk"),
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · clip(0.7·er_mom + 0.3·lowvol, ±1.0)ᵢ)",
             "meaning": "Nghiêng danh mục nền ERC về mã điểm cao, với biên độ nghiêng đã bị đóng khung ở "
                        "bước trên — danh mục rộng, rủi ro cân bằng, không dồn vào một mã."},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["SCORE_CAP là núm vặn chính: hạ → danh mục ổn định/đa dạng hơn; nới → nghiêng mạnh hơn về mã điểm cao; đặt rất lớn = nghiêng tự do theo điểm z (bỏ kẹp)",
                            "⚠️ Đây là GIẢM NHẸ, không phải chặn cứng mức nhảy tỉ trọng: mã MỚI VÀO rổ FTSE vẫn đi từ 0% lên thẳng tỉ trọng mục tiêu. Muốn bảo đảm cứng phải chặn ở tầng lệnh (trần Δw), không làm được trong allocate()",
                            "⚠️ Cửa sổ ER=20 là tham số nhạy. Cap khuyến nghị 25%"],
    },
    "erc_mom_er_v4": {
        "title": "ERC + Momentum chất lượng, chặn biên độ nghiêng + TRẦN DỊCH CHUYỂN MỖI KỲ",
        "summary": "Danh mục cân bằng rủi ro (ERC) nghiêng về momentum chất lượng (momentum 150 phiên nhân "
                   "Kaufman Efficiency Ratio, cộng điểm ổn định giá), có KẸP ĐIỂM để đóng khung biên độ "
                   "nghiêng, VÀ thêm một ràng buộc ở TẦNG LỆNH: tại mỗi phiên rebalance, không mã nào được "
                   "dịch quá max_move điểm % tỉ trọng so với tỉ trọng đang nắm. Ràng buộc tầng lệnh này là "
                   "thứ duy nhất chặn được cú nhảy tỉ trọng đơn lẻ (ví dụ mã mới vào rổ FTSE đi thẳng từ "
                   "0% lên tỉ trọng mục tiêu), vì bước chấm điểm/nghiêng không nhìn thấy tỉ trọng đang nắm. "
                   "Bản dành cho mandate có ràng buộc vận hành/thanh khoản.",
        "components": [
            _ERC,
            {**_ER_MOM, "formula": "er_momᵢ = z( momᵢ(150 phiên) · ERᵢ(20 phiên) )",
             "meaning": "Momentum 150 phiên nhân độ mượt ER — mã tăng đều giữ điểm, mã giật cục bị triệt."},
            _LOWVOL,
            _c("Kẹp điểm số trước khi tilt (SCORE_CAP = 1.0)",
               "scoreᵢ ← clip(scoreᵢ, −1.0, +1.0)",
               "Đóng khung chênh lệch hệ số nghiêng ở exp(2·λ·SCORE_CAP), để một mã điểm cực đoan không bị "
               "đẩy weight lên sát trần cap.", "risk"),
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · clip(0.7·er_mom + 0.3·lowvol, ±1.0)ᵢ)",
             "meaning": "Nghiêng danh mục nền ERC về mã điểm cao, biên độ đã bị đóng khung ở bước trên."},
            _c("⭐ Trần dịch chuyển từng mã mỗi kỳ (move_policy='maxmove', max_move = 10%)",
               "wᵢ ← clip(targetᵢ, max(driftᵢ − 10%, 0), driftᵢ + 10%);  phần bị cắt đẩy sang các mã còn "
               "dư địa theo waterfall để Σw = 1 (KHÔNG chuẩn hóa — chuẩn hóa sẽ scale mọi mã và phá trần)",
               "`drift` là tỉ trọng ĐÃ TRÔI THEO GIÁ tới ngay trước phiên rebalance (tỉ trọng thực đang "
               "nắm), KHÔNG phải target đặt ra ở đầu kỳ trước. Đây là thứ duy nhất chặn được cú nhảy đơn "
               "lẻ. Siết chặt (max_move nhỏ) → dịch chuyển và turnover mỗi kỳ nhỏ hơn, nhưng danh mục "
               "CHẬM bám tín hiệu; trần này bản chất là ĐỘ TRỄ, không phải công cụ giảm rủi ro — đúng lúc "
               "cần thoát nhanh thì bị trói.", "rebalance"),
        ],
        "rebalance": "Hàng tháng, trần dịch chuyển 10 điểm %/mã mỗi kỳ (đo trên tỉ trọng đã drift).",
        "recommendations": ["Chỉ dùng khi có ràng buộc vận hành/thanh khoản buộc giới hạn lệnh mỗi kỳ",
                            "max_move là núm vặn chính: siết chặt → danh mục ổn định, ít giao dịch nhưng bám tín hiệu chậm; nới → bám sát hơn, dịch chuyển lớn hơn",
                            "⚠️ Trần có MỘT ngoại lệ chủ ý: mã RỚT khỏi rổ FTSE bị bán sạch bất kể trần (bắt buộc để universe luôn = rổ FTSE), và việc bán đó kéo tỉ trọng các mã còn lại giãn ra — khi nhiều mã rời rổ cùng kỳ, dịch chuyển thực tế của một mã có thể vượt max_move. Ngoài ngoại lệ đó trần đúng tuyệt đối",
                            "⚠️ Cửa sổ ER=20 là tham số nhạy. Cap khuyến nghị 25%"],
    },
    "erc_mom_er_v5": {
        "title": "ERC + Momentum chất lượng + CASH BẬC THANG theo regime — SDI-compatible, hàng tháng",
        "summary": "Bản erc_mom_er_v3 (danh mục cân bằng rủi ro ERC nghiêng về momentum tăng MƯỢT — Kaufman "
                   "Efficiency Ratio lọc momentum ảo, có kẹp điểm ±1 để một mã không bị đẩy sát trần) cộng "
                   "LÁ CHẮN TIỀN MẶT BẬC THANG: khi FTSE gãy MA100 (xác nhận 5 phiên) rút về 50% cash, nhưng "
                   "exposure chỉ đổi ĐÚNG TẠI KỲ REBALANCE THÁNG — mọi weight version nằm trên lịch, không "
                   "version khẩn cấp, không trade về đích hàng ngày — nên user SDI tracking theo được. Đo "
                   "2020→2026-07: drawdown −37% → −21.1%, Sharpe 1.45 → 1.62, return 32.8% → 31.9%/năm (GROSS).",
        "components": [
            _ERC,
            {**_ER_MOM, "formula": "er_momᵢ = z( momᵢ(150 phiên) · ERᵢ(20 phiên) )",
             "meaning": "Momentum 150 phiên nhân độ mượt ER — mã tăng đều giữ điểm, mã giật cục bị triệt. "
                        "Nguồn return chính."},
            _LOWVOL,
            _c("Kẹp điểm số trước khi tilt (SCORE_CAP = 1.0)",
               "scoreᵢ ← clip(scoreᵢ, −1.0, +1.0)",
               "Đóng khung hệ số nghiêng ở exp(2·λ·SCORE_CAP) để một mã điểm cực đoan không bị đẩy sát trần cap.",
               "risk"),
            {**_TILT, "formula": "wᵢ = ercᵢ · exp(2.0 · clip(0.7·er_mom + 0.3·lowvol, ±1.0)ᵢ)",
             "meaning": "Nghiêng danh mục nền ERC về mã điểm cao, biên độ đã đóng khung. Rổ rộng ~15-20 mã."},
            _c("⭐ Cash bậc thang theo regime (FTSE vs MA100, xác nhận 5 phiên)",
               "tín hiệuₜ = 1(FTSEₜ₋₁ ≥ MA100), trạng thái phải giữ 5 phiên liên tục mới công nhận; "
               "exposure mục tiêu ∈ {0.5, 1.0}, chỉ ĐẶT LẠI đúng ngày rebalance tháng; "
               "giữa hai kỳ cash buy-and-hold → exposure trôi theo giá.",
               "Uptrend → đầu tư đầy; downtrend xác nhận → 50% cổ phiếu + 50% tiền mặt. Khác overlay daily: "
               "mỗi lần đổi exposure là MỘT weight version nằm đúng lịch tháng (~2-3 lần/năm), user tracking "
               "theo được và không phát sinh chi phí trade cash hàng ngày. Vùng tham số robust: MA 100-150 × "
               "xác nhận 3-8 phiên đều cho DD −20…−25%; floor 0.5 là giới hạn sản phẩm (không rút quá 50%).",
               "rebalance"),
        ],
        "rebalance": "Hàng tháng, no-trade band 5%; exposure cash chỉ đặt lại đúng ngày rebalance tháng theo "
                     "trạng thái FTSE vs MA100 (xác nhận 5 phiên) — KHÔNG đổi tỉ trọng hàng ngày, không version khẩn cấp.",
        "recommendations": ["Bản SDI: user tracking theo weight version được, mọi version nằm trên lịch tháng; DD −21% vs −37% full-invested, đổi ~1pp return/năm",
                            "regime_confirm 5 phiên là điểm cân bằng (3-8 đều ổn); muốn phản xạ nhanh hơn ở sập/hồi chữ V: regime_step=\"trigger\" thêm version khẩn cấp giữa kỳ (~3.5 lần/năm) → 33.0%/năm, Sharpe 1.72, DD −23.4% — cần luồng phê duyệt khẩn cấp (BRD 7.5)",
                            "Muốn phòng thủ sâu hơn cho tài khoản cá nhân (KHÔNG phải SDI): floor thấp + overlay daily như bản v5 cũ cắt DD về ~−17% nhưng đổi tỉ trọng hàng ngày",
                            "⚠️ Metrics GROSS: chưa trừ phí/thuế/slippage/T+2.5; cash trong mô phỏng không sinh lời. Chạy thật nên khớp giá mở (ATO) ngày rebalance, ứng trước tiền bán, và bỏ vị thế mục tiêu <3% cho dễ khớp lô",
                            "⚠️ Cửa sổ ER=20 là tham số nhạy. Cap khuyến nghị 25%"],
    },
    "mom_er_liqshare": {
        "title": "Momentum chất lượng cô đặc + trần thanh khoản — luôn full cổ phiếu, hàng tháng",
        "summary": "Danh mục TẤN CÔNG 5-7 mã dẫn dắt có xu hướng tăng MƯỢT (momentum 150 phiên × Kaufman "
                   "Efficiency Ratio — lọc bỏ momentum ảo do giật cục), với TRẦN KÉP: mỗi mã ≤30% danh mục "
                   "VÀ ≤9× tỉ trọng thanh khoản của mã trong rổ — mã thanh khoản thấp không thể chiếm tỉ "
                   "trọng lớn, danh mục tradable ở mọi quy mô vốn. Luôn ~100% cổ phiếu (không giữ cash).",
        "components": [
            {**_ER_MOM, "formula": "er_momᵢ = z( momᵢ(150 phiên) · ERᵢ(20 phiên) )",
             "meaning": "Momentum 150 phiên nhân với độ mượt ER: mã tăng đều đặn giữ nguyên điểm, mã tăng "
                        "nhờ vài phiên giật cục bị triệt về ~0. Vì chiến lược không có nền phòng thủ riêng, "
                        "bộ lọc chất lượng này chính là tầng quản trị rủi ro chủ lực."},
            _LOWVOL,
            {**_TILT, "formula": "wᵢ = exp(16 · (0.65·er_mom + 0.35·lowvol)ᵢ) / Σ",
             "meaning": "Hệ số 16 rất mạnh — thực chất là CHỌN ~5 mã điểm cao nhất thay vì nghiêng nhẹ. "
                        "Danh mục cô đặc, tracking error cao — đây là lựa chọn chủ đích để tối đa return."},
            _c("⭐ Trần kép: 30%/mã VÀ trần thanh khoản (lặp tới hội tụ)",
               "trầnᵢ = min(30%, max(0.5%, 9 · ADTVᵢ/ΣADTV));  lặp [cap 30% → trần thanh khoản] 10 vòng",
               "Tỉ trọng tối đa của mỗi mã tỉ lệ với THANH KHOẢN của chính nó → lệnh mua/bán khi rebalance "
               "tự cân xứng với khả năng hấp thụ của thị trường, không cần nhập AUM; phần vượt trần tự "
               "chảy sang mã thanh khoản cao hơn. Hai trần được lặp tới hội tụ ngay trong chiến lược để "
               "không bước xử lý nào phía sau phá vỡ ràng buộc.", "risk"),
            _c("⭐ Sàn thanh khoản (adtv_floor_bn = 5)",
               "wᵢ = 0 nếu ADTVᵢ < 5 tỷ/phiên (áp trên toàn danh mục, kể cả mã giữ thụ động)",
               "Loại hẳn các mã thanh khoản quá thấp khỏi danh mục — tránh kẹt vị thế không thoát được.",
               "risk"),
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%. Luôn ~100% cổ phiếu (không có cơ chế rút về cash).",
        "recommendations": ["Config cap NÊN đặt 30% (khớp trần trong code). Muốn danh mục đa dạng, TE thấp hơn → xem erc_mom_er_v2",
                            "⚠️ 5-7 mã → rủi ro sự kiện đơn lẻ cao; ER=20 là tham số nhạy; ADTV đo 60 phiên gần nhất (không point-in-time); tỉ trọng có thể vượt trần vài pp do giá chạy giữa 2 kỳ"],
    },
    "semi_erc_mom_er": {
        "title": "Semi-ERC + Kaufman ER-Momentum/DownVol Tilt (hàng tháng)",
        "summary": "Như semi_erc_mom_monthly (nền ERC trên semi-covariance nghiêng momentum + downside-vol) "
                   "NHƯNG thay momentum THÔ bằng KAUFMAN EFFICIENCY RATIO momentum (nhân trọng số theo độ mượt "
                   "của trend). Phòng thủ kép (semi-cov + lọc trend chất lượng).",
        "components": [
            _ER_MOM, _DOWNVOL,
            _c("Semi-ERC (ERC trên semi-covariance)",
               "Σ⁻ = semi-cov chỉ tính từ return ÂM (252 ngày); chọn w sao cho đóng góp DOWNSIDE-risk bằng nhau",
               "Như ERC nhưng đo rủi ro chỉ bằng biến động GIẢM → phòng thủ hơn, không phạt upside.", "risk"),
            {**_TILT, "formula": "wᵢ = baseᵢ · exp(2.0 · (0.5·er_mom + 0.5·downvol)ᵢ),  base = ERC trên semi-cov"},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Khác semi_erc thuần ở chỗ lọc momentum theo độ mượt của xu hướng (Kaufman ER)",
                            "Phòng thủ kép: semi-covariance ở nền + lọc trend chất lượng ở score; ER_WIN=20",
                            "⚠️ Underweight VIC → dòng phòng thủ. Muốn cắt drawdown sâu hơn: + cash overlay. Cap 25-30%"],
    },
    "beta_trig": {
        "title": "Momentum + DownVol + Low-Beta Tilt, có Trigger tập trung",
        "summary": "Tilt FTSE theo 3 factor (momentum, ít rủi ro giảm, beta thấp); rebalance tháng + trim sớm khi 1 mã phình.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE.", "other"),
            _MOM, _DOWNVOL,
            _c("Low-beta score",
               "lowbetaᵢ = z( −βᵢ ),  βᵢ = cov(rᵢ, r_market)/var(r_market)  (market = equal-weight)",
               "Ưu tiên mã ÍT nhạy thị trường (betting-against-beta) → phòng thủ, giảm biến động danh mục.",
               "risk"),
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(2.5 · (0.4·mom + 0.3·downvol + 0.3·lowbeta)ᵢ)"},
            _c("Trigger tập trung + cooldown",
               "rebalance nếu: (đầu tháng) HOẶC (max weight > 20%);  nhưng 2 lần cách nhau ≥ 15 phiên",
               "Khi 1 mã phình > 20% danh mục thì trim sớm (giảm rủi ro tập trung), nhưng cooldown 15 "
               "phiên áp cho CẢ lịch tháng lẫn trigger → không giao dịch quá gần nhau.",
               "rebalance"),
        ],
        "rebalance": "Hàng tháng + trigger khi top holding > 20%; cooldown tối thiểu 15 phiên; band 1.5%.",
        "recommendations": ["3 factor + trigger trim khi tập trung; nền là rổ FTSE", "KHUYẾN NGHỊ cap 35%"],
    },
    "semi_erc_mom_monthly": {
        "title": "Semi-ERC + Momentum/DownVol Tilt (hàng tháng)",
        "summary": "ERC trên SEMI-covariance (chỉ rủi ro giảm) + tilt momentum — thiên phòng thủ. Rebalance hàng tháng.",
        "components": [
            _c("Nền ERC trên semi-covariance",
               "Σ⁻ = ( min(r,0)ᵀ · min(r,0) ) / n · 252;  rồi ERC: wᵢ·(Σ⁻w)ᵢ = const",
               "Equal-Risk nhưng đo trên rủi ro GIẢM (chỉ ngày âm), bỏ qua biến động tăng → "
               "ưu tiên mã rơi ít khi thị trường xấu → drawdown thấp.",
               "risk"),
            _MOM, _DOWNVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ⁻ · exp(2.0 · (0.5·mom + 0.5·downvol)ᵢ)"},
        ],
        "rebalance": "Hàng tháng, no-trade band 1.5%.",
        "recommendations": ["Phòng thủ (đo rủi ro chỉ trên biến động giảm)", "KHUYẾN NGHỊ cap 30%", "Thiết kế gốc chạy ở nhịp THÁNG"],
    },
    "semi_erc_mom_quarterly": {
        "title": "Semi-ERC + Momentum/DownVol Tilt (hàng quý)",
        "summary": "Y hệt bản hàng tháng (ERC semi-covariance + tilt momentum/downvol) nhưng rebalance hàng quý — turnover/phí thấp hơn, bám tín hiệu chậm hơn.",
        "components": [
            _c("Nền ERC trên semi-covariance",
               "Σ⁻ = ( min(r,0)ᵀ · min(r,0) ) / n · 252;  rồi ERC: wᵢ·(Σ⁻w)ᵢ = const",
               "Equal-Risk nhưng đo trên rủi ro GIẢM (chỉ ngày âm), bỏ qua biến động tăng → "
               "ưu tiên mã rơi ít khi thị trường xấu → drawdown thấp.",
               "risk"),
            _MOM, _DOWNVOL,
            {**_TILT, "formula": "wᵢ = ercᵢ⁻ · exp(2.0 · (0.5·mom + 0.5·downvol)ᵢ)"},
        ],
        "rebalance": "Hàng quý, no-trade band 1.5%.",
        "recommendations": ["Turnover/phí thấp hơn bản tháng", "Thiết kế gốc chạy ở nhịp THÁNG → chạy backtest cả hai để đối chiếu", "KHUYẾN NGHỊ cap 30%"],
    },
    "gate_beta": {
        "title": "Gated Beta Tilt — 3 factor + Per-Stock Trend Gate",
        "summary": "Tilt FTSE theo momentum + downside-vol + LOW-BETA (nghiêng phòng thủ) NHƯNG có "
                   "'cổng' theo xu hướng TỪNG MÃ: mã đang dưới MA150 của chính nó bị giảm mạnh tilt → "
                   "tự né cổ phiếu downtrend trong crash.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE (giữ exposure megacap như VIC → bám return).", "other"),
            _MOM, _DOWNVOL,
            _c("Low-beta score (nặng)",
               "lowbetaᵢ = z( −βᵢ ),  βᵢ = cov(rᵢ, r_market)/var(r_market);  trọng số 0.4 (cao nhất)",
               "Ưu tiên mã ÍT nhạy thị trường (betting-against-beta) → phòng thủ, giảm biến động danh mục.", "risk"),
            _c("Per-stock trend gate (điểm mới)",
               "gateᵢ = 1 nếu giáᵢ > MA150ᵢ, ngược lại 0.3;  score_tiltᵢ = scoreᵢ · gateᵢ",
               "Mỗi mã tự xét xu hướng RIÊNG: mã dưới MA150 của chính nó → tilt bị nén về sát anchor "
               "(không đặt cược). Trong crash đa số mã downtrend → danh mục tự rút về phòng thủ mà KHÔNG "
               "cần market-timing toàn cục (vốn hay lag, bỏ lỡ hồi phục). Đây là chìa khóa cắt drawdown.",
               "risk"),
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(2.5 · gateᵢ · (0.3·mom + 0.3·downvol + 0.4·lowbeta)ᵢ)"},
            _c("Trigger tập trung + cooldown",
               "rebalance nếu: (đầu tháng) HOẶC (max weight > 20%); 2 lần cách nhau ≥ 15 phiên",
               "Trim sớm khi 1 mã phình > 20% (giảm rủi ro tập trung); cooldown 15 phiên cho cả lịch lẫn trigger.",
               "rebalance"),
        ],
        "rebalance": "Hàng tháng + trigger khi top holding > 20%; cooldown ≥ 15 phiên; band 1.5%.",
        "recommendations": ["Gate MA150 từng mã gánh phần phòng thủ, không cần market-timing toàn cục", "Turnover cao → cân nhắc phí", "KHUYẾN NGHỊ cap 35%"],
    },
    "gate_beta_dd": {
        "title": "Gated Beta Tilt — biến thể GIẢM DRAWDOWN",
        "summary": "Như gate_beta (per-stock trend gate) nhưng trọng số nghiêng momentum + downside-vol "
                   "(0.45/0.35/0.2) — low-beta nhẹ đi, gate MA150 gánh phần phòng thủ.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE.", "other"),
            _MOM, _DOWNVOL,
            _c("Low-beta score (nhẹ)", "lowbetaᵢ = z(−βᵢ); trọng số 0.2",
               "Vẫn ưu tiên beta thấp nhưng nhẹ hơn gate_beta — nhường chỗ momentum/downvol.", "risk"),
            _c("Per-stock trend gate (điểm mới)",
               "gateᵢ = 1 nếu giáᵢ > MA150ᵢ, ngược lại 0.3;  score_tiltᵢ = scoreᵢ · gateᵢ",
               "Cổng theo xu hướng từng mã: nén tilt cho mã dưới MA riêng → né loser downtrend, cắt drawdown.", "risk"),
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(2.5 · gateᵢ · (0.45·mom + 0.35·downvol + 0.2·lowbeta)ᵢ)"},
            _c("Trigger tập trung + cooldown",
               "rebalance nếu: (đầu tháng) HOẶC (max weight > 20%); 2 lần cách nhau ≥ 15 phiên",
               "Trim sớm khi 1 mã phình > 20%; cooldown 15 phiên.", "rebalance"),
        ],
        "rebalance": "Hàng tháng + trigger khi top holding > 20%; cooldown ≥ 15 phiên; band 1.5%.",
        "recommendations": ["Biến thể nghiêng phòng thủ của gate_beta (low-beta 0.2 thay vì 0.4)", "KHUYẾN NGHỊ cap 35%"],
    },
    "gate_beta_v2": {
        "title": "Gated Beta Tilt V2 — gate mạnh + tilt mạnh",
        "summary": "Bản tăng lực của gate_beta: cùng 3 factor (0.3 mom / 0.3 downvol / 0.4 low-beta) "
                   "nhưng GATE MẠNH HƠN (mã dưới MA150 bị nén ×0.1 thay vì ×0.3) và TILT MẠNH HƠN (λ=3.0). "
                   "Né loser downtrend quyết liệt hơn + bám VIC/winner đậm hơn.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE (giữ exposure megacap như VIC).", "other"),
            _MOM, _DOWNVOL,
            _c("Low-beta score (nặng)",
               "lowbetaᵢ = z(−βᵢ), βᵢ = cov(rᵢ, r_market)/var(r_market); trọng số 0.4",
               "Ưu tiên mã ít nhạy thị trường (betting-against-beta) → giảm biến động danh mục.", "risk"),
            _c("Per-stock trend gate MẠNH (×0.1)",
               "gateᵢ = 1 nếu giáᵢ > MA150ᵢ, ngược lại 0.1;  score_tiltᵢ = scoreᵢ · gateᵢ",
               "Cổng theo xu hướng TỪNG MÃ nhưng nén mạnh hơn gate_beta (0.1 thay vì 0.3): mã dưới MA "
               "riêng gần như rút hết tilt về anchor → né downtrend quyết liệt trong crash, cắt drawdown.",
               "risk"),
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(3.0 · gateᵢ · (0.3·mom + 0.3·downvol + 0.4·lowbeta)ᵢ)"},
            _c("Trigger tập trung + cooldown",
               "rebalance nếu: (đầu tháng) HOẶC (max weight > 20%); 2 lần cách nhau ≥ 15 phiên",
               "Trim sớm khi 1 mã phình > 20%; cooldown 15 phiên cho cả lịch lẫn trigger.", "rebalance"),
        ],
        "rebalance": "Hàng tháng + trigger khi top holding > 20%; cooldown ≥ 15 phiên; band 1.5%.",
        "recommendations": ["Bản tăng lực của gate_beta: gate ×0.1 (thay vì ×0.3) và λ=3.0 (thay vì 2.5)",
                            "⚠️ Cần cap CAO để giữ VIC: KHUYẾN NGHỊ cap 35%",
                            "Turnover cao → cân nhắc phí"],
    },
    "gate_beta_guard": {
        "title": "Gated Beta Guard — gate_beta_v2 + Market-Timing Cash Overlay",
        "summary": "Composition y hệt gate_beta_v2 (3 factor 0.3 mom / 0.3 downvol / 0.4 low-beta + "
                   "per-stock trend gate MA150 ×0.1, tilt λ=3.0) + OVERLAY TIỀN MẶT: khi FTSE index < "
                   "MA200 thì giảm gross exposure về regime_floor (phần còn lại cash). ⚠️ HIỆN "
                   "regime_floor = 0.9 → risk-off vẫn giữ 90% đầu tư ⇒ overlay gần như TẮT, chiến lược "
                   "chạy sát gate_beta_v2. Hạ regime_floor về 0.0 để overlay thực sự rút về tiền mặt.",
        "components": [
            _c("Anchor = FTSE benchmark", "anchor = w_bench", "Nền là rổ FTSE (giữ exposure VIC).", "other"),
            _MOM, _DOWNVOL,
            _c("Low-beta score (nặng)",
               "lowbetaᵢ = z(−βᵢ), trọng số 0.4",
               "Ưu tiên mã ít nhạy thị trường → giảm biến động danh mục.", "risk"),
            _c("Per-stock trend gate MẠNH (×0.1)",
               "gateᵢ = 1 nếu giáᵢ > MA150ᵢ, ngược lại 0.1",
               "Mã dưới MA riêng rút tilt về anchor → né downtrend từng mã.", "risk"),
            {**_TILT, "formula": "wᵢ = w_benchᵢ · exp(3.0 · gateᵢ · (0.3·mom + 0.3·downvol + 0.4·lowbeta)ᵢ)"},
            _c("⭐ Market-timing CASH overlay (MA200)",
               "exposureₜ = 1 nếu FTSE_indexₜ₋₁ ≥ MA200ₜ₋₁, ngược lại = regime_floor (HIỆN = 0.9 → gần như tắt overlay; đặt 0.0 để full cash); "
               "port_retₜ = exposureₜ · (w·r)ₜ, phần (1−exposure) giữ tiền mặt (return 0). Signal trễ 1 phiên (no look-ahead).",
               "Đây là điểm khác biệt cốt lõi: rút vốn về cash khi cả thị trường (FTSE) gãy MA200 → "
               "né downtrend toàn thị trường thay vì full-invested. Đây là cơ chế DUY NHẤT trong framework "
               "cho phép giữ tiền mặt (bản full-invested không thể). Đổi lại: TE vs FTSE cao + whipsaw "
               "khi index dập dình quanh MA.", "risk"),
            _c("Trigger tập trung + cooldown",
               "rebalance nếu: (đầu tháng) HOẶC (max weight > 20%); ≥ 15 phiên giữa 2 lần",
               "Trim sớm khi 1 mã phình > 20%.", "rebalance"),
        ],
        "rebalance": "Hàng tháng + trigger >20% (cooldown ≥15 phiên); overlay cash đánh giá HÀNG NGÀY theo FTSE vs MA200.",
        "recommendations": ["⚠️ regime_floor mặc định 0.9 khiến overlay gần như tắt — hạ về 0.0 để rút hẳn về tiền mặt khi risk-off",
                            "regime_floor 0.0 = phòng thủ mạnh nhất (full cash); 0.3 giữ lại một phần đầu tư, ít whipsaw hơn",
                            "⚠️ Market-timing → TE vs FTSE cao + có whipsaw khi index dập dình quanh MA200",
                            "Giữ cash trong pha risk-off nên return thô nhường lại một phần để đổi lấy drawdown nông"],
    },
    "ma20_leaders_bull": {
        "title": "MA20-Leaders BULL — Top-5 cổ phiếu dẫn dắt, tấn công cho pha thị trường tăng",
        "summary": "Danh mục tập trung 5 cổ phiếu DẪN DẮT: giá vượt trội SMA20 (đang hút dòng tiền) "
                   "KẾT HỢP momentum 120 phiên (sức mạnh trung hạn), weight inverse-vol, rebalance TUẦN, "
                   "kèm trailing stop từng mã. Đây là chiến lược ALPHA TẤN CÔNG thuần — KHÔNG có cơ chế "
                   "phòng thủ thị trường; người dùng tự quyết định vào/ra (vd giữ khi FTSE trên MA100). ",
        "components": [
            _c("Score dẫn dắt ngắn hạn (MA20)",
               "s_shortᵢ = z(giáᵢ / SMA20ᵢ)",
               "Giá vượt SMA20 càng xa = cổ phiếu đang dẫn dắt, hút dòng tiền chủ động. "
               "Bản chất là momentum ~1 tháng: nhạy nhưng nhiễu — nên chỉ chiếm 50% score.", "return"),
            _c("Score momentum trung hạn (120 phiên)",
               "s_longᵢ = z(return tích lũy 120 phiên);  score = 0.5·s_short + 0.5·s_long",
               "Lọc leader 'bền': phải mạnh CẢ tháng gần nhất LẪN 6 tháng. Hai tín hiệu chia đều 50/50 "
               "thay vì dùng riêng một tín hiệu.", "return"),
            _c("Top-5 + inverse-vol weight",
               "chọn 5 mã score cao nhất;  wᵢ ∝ 1/vol60ᵢ",
               "Tập trung 5 mã để tối đa lợi nhuận (ít mã hơn thì rủi ro tập trung quá cao, nhiều mã hơn "
               "thì loãng alpha); trong rổ, mã biến động thấp được weight cao hơn → đỡ sốc từng mã.", "return"),
            _c("Trailing stop 120/15% + guard chống tập trung",
               "mã rớt >15% từ đỉnh 120 phiên → w=0; nếu còn <3 mã sống → cắt mềm ×0.3",
               "Stop-loss động cắt leader gãy trend, vốn dồn sang mã khỏe. GUARD quan trọng: không có nó, "
               "trong bear stop cắt gần hết rổ → danh mục dồn phần lớn vào 1-2 mã sống sót (rủi ro tập trung).", "risk"),
            _c("Liquidity-share cap λ7 + ADTV floor 5 tỷ",
               "capᵢ = max(0.5%, 7·ADTVᵢ/ΣADTV);  wᵢ=0 nếu ADTVᵢ<5 tỷ",
               "Rổ 5 mã ~20%/mã → PHẢI chặn cấu trúc theo thanh khoản để trade được ở mọi AUM.", "risk"),
        ],
        "rebalance": "Mỗi 5 phiên (tuần), no-trade band 2%.",
        "recommendations": ["DÙNG KHI THỊ TRƯỜNG TĂNG và bạn tự kỷ luật vào/ra (vd giữ khi FTSE trên MA100)",
                            "⚠️ TUYỆT ĐỐI không cầm xuyên downtrend: chiến lược KHÔNG có tầng phòng thủ thị trường",
                            "⚠️ Yếu khi thị trường mean-reversion — đặc tính cố hữu của lối đuổi leader",
                            "Muốn bản tự phòng thủ, không cần tự timing → xem ma20_leaders_allweather",
                            "5 mã, TE rất cao — chiến lược alpha cá nhân, không phải sản phẩm bám benchmark. Cap 35%"],
    },
    "ma20_leaders_allweather": {
        "title": "MA20-Leaders ALL-WEATHER — Top-5 cổ phiếu dẫn dắt TỰ PHÒNG THỦ, dùng mọi thời điểm",
        "summary": "Danh mục tập trung 5 cổ phiếu DẪN DẮT (giá vượt trội SMA20 + momentum trung hạn) có "
                   "3 TẦNG PHÒNG THỦ TỰ ĐỘNG: lọc chất lượng từng mã (gate MA150 + momentum bỏ-tháng-cuối), "
                   "stop-loss động từng mã, và cash overlay toàn danh mục theo 2 đường MA của index — "
                   "KHÔNG cần người dùng timing thị trường. Rebalance TUẦN, weight inverse-vol. ",
        "components": [
            _c("Score dẫn dắt ngắn hạn (MA20)",
               "s_shortᵢ = z(giáᵢ / SMA20ᵢ)",
               "Giá vượt SMA20 càng xa = cổ phiếu đang dẫn dắt, hút dòng tiền chủ động. Nhạy nhưng "
               "nhiễu — chỉ chiếm 50% score, nửa còn lại là momentum trung hạn.", "return"),
            _c("Score momentum skip-month (kiểu '12-1')",
               "s_longᵢ = z(giáᵢ(t-22) / giáᵢ(t-121) − 1)  — BỎ 21 phiên gần nhất;  score = 0.5·s_short + 0.5·s_long",
               "Đo sức mạnh trung hạn nhưng BỎ tháng cuối vì tháng gần nhất của cổ phiếu hay đảo chiều "
               "ngắn hạn (mean-reversion) — cách chuẩn học thuật để né momentum-crash. Đây là tầng lọc "
               "chất lượng chính giúp chiến lược chịu được các pha thị trường xấu.", "return"),
            _c("Per-stock MA150 gate ×0.5",
               "scoreᵢ ×= 0.5 nếu giáᵢ < MA150ᵢ",
               "Mã mạnh ngắn hạn nhưng đang DƯỚI nền giá dài hạn của chính nó = ứng viên bull-trap → "
               "giảm nửa score. Vùng MA120-200 cho kết quả như nhau (không nhạy tham số).", "risk"),
            _c("Top-5 + inverse-vol weight",
               "chọn 5 mã score cao nhất;  wᵢ ∝ 1/vol60ᵢ",
               "Tập trung 5 mã để tối đa lợi nhuận; trong rổ, mã biến động thấp được weight cao hơn.", "return"),
            _c("Trailing stop 120/15% + guard chống tập trung",
               "mã rớt >15% từ đỉnh 120 phiên → w=0; nếu còn <3 mã sống → cắt mềm ×0.3",
               "Stop-loss động cắt mã gãy trend, vốn dồn sang mã khỏe; guard tránh dồn danh mục vào "
               "1-2 mã sống sót khi thị trường xấu cắt gần hết rổ.", "risk"),
            _c("Cash overlay dual-MA (MA20 + MA100 của index, floor 0.2)",
               "exposureₜ = 0.2 + 0.4·1(FTSEₜ₋₁≥MA20) + 0.4·1(FTSEₜ₋₁≥MA100) ∈ {0.2, 0.6, 1.0}",
               "Tầng phòng thủ toàn danh mục, đánh giá hàng ngày (tín hiệu trễ 1 phiên): correction nhanh "
               "(index gãy MA20 nhưng còn trên MA100) → giữ 60% đầu tư nên không lỡ nhịp hồi chữ V; gãy "
               "cả 2 đường (downtrend thật) → chỉ còn 20% đầu tư, 80% tiền mặt.", "risk"),
            _c("Liquidity-share cap λ7 + ADTV floor 5 tỷ",
               "capᵢ = max(0.5%, 7·ADTVᵢ/ΣADTV);  wᵢ=0 nếu ADTVᵢ<5 tỷ",
               "Rổ 5 mã ~20%/mã → chặn cấu trúc theo thanh khoản để trade được ở mọi AUM.", "risk"),
        ],
        "rebalance": "Mỗi 5 phiên (tuần), no-trade band 2%; cash overlay đánh giá HÀNG NGÀY theo FTSE vs MA20/MA100.",
        "recommendations": ["Dùng được mọi thời điểm — 3 tầng phòng thủ tự động, không cần người dùng tự timing",
                            "Khác ma20_leaders_bull ở: gate MA150, momentum skip-month, và cash overlay dual-MA",
                            "⚠️ Lag index khi thị trường mean-reversion mạnh — đặc tính cố hữu của lối đuổi leader",
                            "5 mã, TE rất cao — chiến lược alpha cá nhân, không phải sản phẩm bám benchmark. Cap 35%"],
    },
}


# LLM path, for generated or custom strategies
_PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "strategy_explain.md").read_text(encoding="utf-8")
_EXPLAIN_CACHE: dict[str, dict] = {}
_CACHE_MAX = 64
_REQUIRED_KEYS = {"title", "summary", "components", "rebalance", "recommendations"}


def _explain_via_llm(code: str, model: str | None = None) -> dict:
    from app.lab.codegen import _llm, _strip_fences
    from app.lab.llm import default_model

    model = model or default_model()
    prompt = _PROMPT_TEMPLATE.format(code=code)

    def _parse(raw: str) -> dict:
        obj = json.loads(_strip_fences(raw))
        if not _REQUIRED_KEYS.issubset(obj):
            raise ValueError(f"Thiếu key: {_REQUIRED_KEYS - set(obj)}")
        return obj

    try:
        return _parse(_llm(prompt, model))
    except Exception as exc:  # retry once, feeding the error back
        fix = prompt + f"\n\n# Lần trước SAI: {exc}\nXuất lại CHỈ JSON hợp lệ đúng schema."
        return _parse(_llm(fix, model))


# Public API

def explain(spec: dict[str, Any], config: LabConfig | None = None,
            model: str | None = None) -> dict:
    """Explain one strategy: curated text for presets, otherwise the LLM, cached."""
    preset = spec.get("preset")
    if preset and preset in PRESET_EXPLANATIONS:
        return PRESET_EXPLANATIONS[preset]

    from app.lab.runner import _resolve_code
    code = _resolve_code(spec)

    # code identical to a known preset: use its curated text
    from app.lab.presets import PRESETS
    for name, preset_code in PRESETS.items():
        if name in PRESET_EXPLANATIONS and preset_code.strip() == code.strip():
            return PRESET_EXPLANATIONS[name]

    h = hashlib.sha1(code.encode()).hexdigest()[:16]
    if h not in _EXPLAIN_CACHE:
        if len(_EXPLAIN_CACHE) >= _CACHE_MAX:
            _EXPLAIN_CACHE.pop(next(iter(_EXPLAIN_CACHE)))
        _EXPLAIN_CACHE[h] = _explain_via_llm(code, model)
    return _EXPLAIN_CACHE[h]
