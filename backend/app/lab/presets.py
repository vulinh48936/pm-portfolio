"""Built-in strategies: a comparison library and the few-shot examples for codegen.

Each preset is a code string that goes through the same validate-and-load path as
generated code, which is why the same text can be used as a prompt example.

The docstring inside each preset is shown to the PM in the code box, so it stays in
Vietnamese.
"""

from __future__ import annotations

RISK_PARITY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity

class RiskParityStrategy(Strategy):
    """Equal Risk Contribution: mỗi mã gánh rủi ro bằng nhau. Rebalance quý, band 1.5%."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        return risk_parity(Sigma=feat.cov(252))
'''

RISK_PARITY_MONTHLY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity

class RiskParityMonthlyStrategy(Strategy):
    """Equal Risk Contribution: mỗi mã gánh rủi ro bằng nhau. Giống risk_parity nhưng
    rebalance HÀNG THÁNG (bám rủi ro sát hơn, turnover cao hơn). Band 1.5%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        return risk_parity(Sigma=feat.cov(252))
'''

RISK_PARITY_DD = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity

class RiskParityDDStrategy(Strategy):
    """Risk parity + drawdown gate A: ở kỳ rebalance chỉ giao dịch khi đang
    drawdown (dd < -8%), bỏ qua nếu danh mục đang ổn. Ép rebalance khi 1 mã
    vượt trần 25% (giữ trần cứng). Rebalance quý, band 1.5%."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def should_rebalance(self, ctx):
        if not ctx.is_scheduled:
            return False
        if ctx.max_weight > 0.25:        # override: ép giữ trần cứng
            return True
        return ctx.drawdown < -0.08      # gate A: chỉ rebalance khi đang DD

    def allocate(self, feat, w_bench, ctx):
        return risk_parity(Sigma=feat.cov(252))
'''

MIN_VAR = '''\
from app.lab.strategy import Strategy
from app.lab.lib import min_var

class MinVarStrategy(Strategy):
    """Long-only minimum variance. Rebalance quý, band 1.5%."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        return min_var(Sigma=feat.cov(252), cap=0.25)
'''

FACTOR_TILT = '''\
from app.lab.strategy import Strategy
from app.lab.lib import factor_tilt

class FactorTiltStrategy(Strategy):
    """Tilt FTSE theo momentum + low-vol. Giữ gần benchmark. Rebalance quý."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        return factor_tilt(feat.returns(120), w_bench, tilt_strength=1.0)
'''

MOM_DOWNVOL_TILT = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, tilt

class MomDownVolTiltStrategy(Strategy):
    """Tilt FTSE theo momentum + low DOWNSIDE-vol (semi-deviation): cưỡi winner,
    phạt rủi ro GIẢM (không phạt biến động tăng) → giữ return, cắt drawdown.
    Beat FTSE cả 3 chỉ số (Sharpe/MaxDD/Return) ở cả 2 nửa giai đoạn.
    KHUYẾN NGHỊ cap 35%. Rebalance hàng tháng, band 1.5%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * downvol_score(r, 120)
        return tilt(w_bench, score, 2.5)
'''

ERC_MOM_TILT_MONTHLY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, momentum_score, lowvol_score, tilt

class ERCMomTiltMonthlyStrategy(Strategy):
    """Nền Equal-Risk-Contribution (đa dạng, cân bằng rủi ro) rồi nghiêng nhẹ theo
    momentum + low-vol. Profile PHÒNG THỦ: drawdown thấp hơn nhiều FTSE (~-31% vs -44%),
    thắng đậm giai đoạn gấu. Beat Sharpe + MaxDD.
    KHUYẾN NGHỊ cap 25%. Rebalance hàng tháng, band 1.5%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * lowvol_score(r, 60)
        return tilt(erc, score, 2.0)
'''

ERC_MOM_TILT_QUARTERLY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, momentum_score, lowvol_score, tilt

class ERCMomTiltQuarterlyStrategy(Strategy):
    """Y hệt erc_mom_tilt_monthly (nền ERC nghiêng momentum + low-vol) nhưng rebalance
    HÀNG QUÝ — turnover/phí thấp hơn, bám tín hiệu chậm hơn. KHUYẾN NGHỊ cap 25%. Band 1.5%."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * lowvol_score(r, 60)
        return tilt(erc, score, 2.0)
'''

BETA_TRIG = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, lowbeta_score, tilt

class BetaTrigStrategy(Strategy):
    """Tilt FTSE theo momentum + downside-vol + low-beta (3 factor, thêm phòng thủ beta).
    Rebalance hàng tháng + TRIGGER: khi 1 mã (top holding) phình > 20% danh mục thì
    rebalance sớm để trim bớt tập trung — nhưng 2 lần rebalance cách nhau tối thiểu 15
    phiên (cooldown, tránh giao dịch quá gần). Beat FTSE cả 3: Sharpe ~1.45, MaxDD ~-38%,
    return ~+30%. KHUYẾN NGHỊ cap 35%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MIN_GAP = 15
    MAX_WEIGHT_TRIGGER = 0.20

    def should_rebalance(self, ctx):
        if ctx.days_since_rebal < self.MIN_GAP:
            return False                                  # cooldown global
        if ctx.is_scheduled:
            return True                                   # định kỳ hàng tháng
        return ctx.max_weight > self.MAX_WEIGHT_TRIGGER   # trigger: mã phình quá

    def allocate(self, feat, w_bench, ctx):
        r = feat.returns(120)
        score = (0.4 * momentum_score(r, 120) + 0.3 * downvol_score(r, 120)
                 + 0.3 * lowbeta_score(r, 120))
        return tilt(w_bench, score, 2.5)
'''

SEMI_ERC_MOM_MONTHLY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, momentum_score, downvol_score, tilt, downside_cov

class SemiERCMomMonthlyStrategy(Strategy):
    """Nền Equal-Risk-Contribution trên SEMI-covariance (cân bằng rủi ro GIẢM, bỏ qua
    biến động tăng) rồi nghiêng momentum + downside-vol. Phòng thủ mạnh: drawdown thấp
    (~-31% vs FTSE -44%) NHƯNG Sharpe cao (~1.40). Thắng đậm giai đoạn gấu (2022).
    Beat Sharpe + MaxDD. KHUYẾN NGHỊ cap 30%. Rebalance hàng tháng, band 1.5%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        base = risk_parity(Sigma=downside_cov(feat.returns(252), 252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * downvol_score(r, 120)
        return tilt(base, score, 2.0)
'''

SEMI_ERC_MOM_QUARTERLY = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, momentum_score, downvol_score, tilt, downside_cov

class SemiERCMomQuarterlyStrategy(Strategy):
    """Y hệt semi_erc_mom_monthly (nền ERC semi-covariance nghiêng momentum + downside-vol)
    nhưng rebalance HÀNG QUÝ — turnover/phí thấp hơn, bám tín hiệu chậm hơn.
    KHUYẾN NGHỊ cap 30%. Band 1.5%."""
    rebalance_schedule = "quarterly"
    move_policy = "band"
    band = 0.015

    def allocate(self, feat, w_bench, ctx):
        base = risk_parity(Sigma=downside_cov(feat.returns(252), 252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * downvol_score(r, 120)
        return tilt(base, score, 2.0)
'''

GATE_BETA = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, lowbeta_score, tilt
import numpy as np

class GateBetaStrategy(Strategy):
    """Tilt FTSE theo 3 factor NGHIÊNG PHÒNG THỦ (low-beta nặng 0.4 + downside-vol 0.3
    + momentum 0.3) CÓ PER-STOCK TREND GATE: mã đang DƯỚI MA150 của chính nó bị giảm
    mạnh tilt (×0.3) → tự né cổ phiếu downtrend trong crash mà KHÔNG cần market-timing
    (gate theo từng mã nên ít lag hơn tín hiệu thị trường). Rebalance tháng + TRIGGER
    trim khi 1 mã > 20% danh mục (cooldown 15 phiên).
    Beat FTSE CẢ 3 chỉ số BỀN: Sharpe ~1.3 (vs 0.89), MaxDD ~-40% (vs -44%),
    CAGR ~+28% (vs +21%); thắng ở CẢ crash 2020-22 lẫn hồi phục 2023-26.
    KHUYẾN NGHỊ cap 35%, band 1.5%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MIN_GAP = 15
    MAX_WEIGHT_TRIGGER = 0.20
    GATE_WIN = 150
    GATE_LOW = 0.3

    def should_rebalance(self, ctx):
        if ctx.days_since_rebal < self.MIN_GAP:
            return False
        if ctx.is_scheduled:
            return True
        return ctx.max_weight > self.MAX_WEIGHT_TRIGGER

    def allocate(self, feat, w_bench, ctx):
        cl = feat.closes()
        ma = cl[-self.GATE_WIN:].mean(axis=0)
        gate = np.where(cl[-1] > ma, 1.0, self.GATE_LOW)
        r = feat.returns(120)
        score = (0.3 * momentum_score(r, 120) + 0.3 * downvol_score(r, 120)
                 + 0.4 * lowbeta_score(r, 120))
        return tilt(w_bench, score * gate, 2.5)
'''

GATE_BETA_DD = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, lowbeta_score, tilt
import numpy as np

class GateBetaDDStrategy(Strategy):
    """Biến thể GIẢM DRAWDOWN của gate_beta: cùng per-stock trend gate (MA150, ×0.3)
    nhưng trọng số factor nghiêng momentum + downside-vol (0.45 mom / 0.35 downvol /
    0.2 low-beta) — gate gánh phần phòng thủ nên DD vẫn rất nông. MaxDD thấp nhất
    nhóm (~-38% vs FTSE -44%), Sharpe ~1.2, CAGR ~+27% (>FTSE). Beat FTSE cả 3.
    Rebalance tháng + trigger trim > 20% (cooldown 15 phiên). KHUYẾN NGHỊ cap 35%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MIN_GAP = 15
    MAX_WEIGHT_TRIGGER = 0.20
    GATE_WIN = 150
    GATE_LOW = 0.3

    def should_rebalance(self, ctx):
        if ctx.days_since_rebal < self.MIN_GAP:
            return False
        if ctx.is_scheduled:
            return True
        return ctx.max_weight > self.MAX_WEIGHT_TRIGGER

    def allocate(self, feat, w_bench, ctx):
        cl = feat.closes()
        ma = cl[-self.GATE_WIN:].mean(axis=0)
        gate = np.where(cl[-1] > ma, 1.0, self.GATE_LOW)
        r = feat.returns(120)
        score = (0.45 * momentum_score(r, 120) + 0.35 * downvol_score(r, 120)
                 + 0.2 * lowbeta_score(r, 120))
        return tilt(w_bench, score * gate, 2.5)
'''

GATE_BETA_V2 = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, lowbeta_score, tilt
import numpy as np

class GateBetaV2Strategy(Strategy):
    """Bản TĂNG LỰC của gate_beta — tối ưu cho điểm vào 2021 + beat VNINDEX 2026-YTD.
    Cùng cấu trúc (3 factor 0.3 mom / 0.3 downvol / 0.4 low-beta + per-stock trend gate
    MA150) nhưng GATE MẠNH HƠN (mã dưới MA bị nén ×0.1 thay vì ×0.3 → né loser downtrend
    quyết liệt hơn) và TILT MẠNH HƠN (λ=3.0 thay vì 2.5 → bám VIC/winner đậm hơn).
    Từ 2021-01: Sharpe ~1.34 (cap35), CAGR ~+28% (>FTSE +17%), MaxDD ~-40%; beat VNINDEX
    & FTSE ở CẢ pha gấu 2021-22 (strat +7.6% vs VNI -5.8%, FTSE -9%) lẫn hồi 2023-26.
    2026-YTD beat VNINDEX +5.5pp (cap35). Robust mọi entry 2021 (kể cả đỉnh 06/2021).
    ⚠️ Cần cap CAO để giữ VIC (rổ 2026 nặng VIC 39%): KHUYẾN NGHỊ cap 35% (cap25 margin
    2026 mỏng còn +0.4); band 1.5%, trigger trim >20% (cooldown 15 phiên)."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MIN_GAP = 15
    MAX_WEIGHT_TRIGGER = 0.20
    GATE_WIN = 150
    GATE_LOW = 0.1

    def should_rebalance(self, ctx):
        if ctx.days_since_rebal < self.MIN_GAP:
            return False
        if ctx.is_scheduled:
            return True
        return ctx.max_weight > self.MAX_WEIGHT_TRIGGER

    def allocate(self, feat, w_bench, ctx):
        cl = feat.closes()
        ma = cl[-self.GATE_WIN:].mean(axis=0)
        gate = np.where(cl[-1] > ma, 1.0, self.GATE_LOW)
        r = feat.returns(120)
        score = (0.3 * momentum_score(r, 120) + 0.3 * downvol_score(r, 120)
                 + 0.4 * lowbeta_score(r, 120))
        return tilt(w_bench, score * gate, 3.0)
'''

ERC_MOM_TRAIL = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, momentum_score, lowvol_score, tilt, trailing_stop_gate

class ERCMomTrailStrategy(Strategy):
    """erc_mom_tilt_monthly (nền ERC nghiêng momentum + low-vol) + TRAILING-LOSS GATE
    per-stock: mã nào rớt > TRAIL_X (15%) so với ĐỈNH TRAIL_WIN (60) ngày gần nhất thì
    CẮT HẲN tỉ trọng (×0) rồi chia lại cho mã khỏe. Stop-loss động theo từng mã, đánh giá
    mỗi kỳ rebalance (tháng). Vẫn cải thiện CAGR + Sharpe so với erc_mom thuần (DD ~-40% vs
    -45%). ⚠️ LƯU Ý: cửa sổ 60 ngày kém hơn 120 ngày rõ (W120: DD -34% Sh0.90; W60: DD -40%
    Sh0.81) — đỉnh tham chiếu ngắn reset nhanh nên bỏ sót downtrend kéo dài; cân nhắc TRAIL_WIN=120.
    ⚠️ Họ ERC underweight VIC → LAG VNINDEX 2026 (không hợp mục tiêu beat 2026); đây là dòng
    PHÒNG THỦ/drawdown-thấp. Muốn DD<30%: bật thêm cash overlay (regime_floor=0.0). cap 25-30%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    TRAIL_WIN = 60
    TRAIL_X = 0.15
    TRAIL_RED = 0.0

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * lowvol_score(r, 60)
        w = tilt(erc, score, 2.0)
        w = w * trailing_stop_gate(feat.closes(), self.TRAIL_WIN, self.TRAIL_X, self.TRAIL_RED)
        s = w.sum()
        return w / s if s > 0 else erc
'''

SEMI_ERC_MOM_TRAIL = '''\
from app.lab.strategy import Strategy
from app.lab.lib import (risk_parity, momentum_score, downvol_score, tilt,
                         downside_cov, trailing_stop_gate)

class SemiERCMomTrailStrategy(Strategy):
    """semi_erc_mom_monthly (nền ERC trên SEMI-covariance nghiêng momentum + downside-vol)
    + TRAILING-LOSS GATE per-stock: mã rớt > TRAIL_X (15%) so với ĐỈNH TRAIL_WIN (60) ngày
    thì CẮT HẲN (×0) rồi chia lại cho mã khỏe. Phòng thủ kép (semi-cov + stop-loss động).
    Vẫn cải thiện CAGR + Sharpe so với semi_erc thuần (DD ~-42% vs -47%). ⚠️ LƯU Ý: cửa sổ
    60 ngày kém hơn 120 (W120: DD -36% Sh0.95; W60: DD -42% Sh0.86) — đỉnh ngắn bỏ sót
    downtrend kéo dài; cân nhắc TRAIL_WIN=120.
    ⚠️ Underweight VIC → LAG VNINDEX 2026. Dòng PHÒNG THỦ. Muốn DD<30%: + cash overlay. cap 30%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    TRAIL_WIN = 60
    TRAIL_X = 0.15
    TRAIL_RED = 0.0

    def allocate(self, feat, w_bench, ctx):
        base = risk_parity(Sigma=downside_cov(feat.returns(252), 252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * downvol_score(r, 120)
        w = tilt(base, score, 2.0)
        w = w * trailing_stop_gate(feat.closes(), self.TRAIL_WIN, self.TRAIL_X, self.TRAIL_RED)
        s = w.sum()
        return w / s if s > 0 else base
'''

SEMI_ERC_MOM_LIQSHARE = '''\
from app.lab.strategy import Strategy
from app.lab.lib import (risk_parity, momentum_score, downvol_score, tilt,
                         downside_cov, trailing_stop_gate, liquidity_score,
                         liq_share_cap)

class SemiERCMomLiqShareStrategy(Strategy):
    """semi_erc_mom_trail bản THANH KHOẢN-NATIVE (tự xử lý ở tầng weight, KHÔNG cần AUM):
    (1) LIQ-SHARE CAP: trần weight mỗi mã = LAM · ADTVᵢ/ΣADTV — mã thanh khoản thấp bị
    chặn cấu trúc, weight tỉ lệ thanh khoản → trade ∝ ADTV → spill-days ĐỀU nhau mọi mã
    ở MỌI AUM (không mã nào thành nút thắt). Có feasibility-scaling: bear market trailing
    gate cắt gần hết rổ → caps tự nới tỉ lệ, overflow chảy vào mã thanh khoản NHẤT
    (fix sự kiện SAB +22.5%/kỳ 2022-12). (2) LIQUIDITY TILT 15%: score nghiêng nhẹ về
    mã dễ trade. (3) adtv_floor_bn=5 tự khai: engine loại mã ADTV<5 tỷ TRÊN TOÀN vector,
    gồm cả mã passive short-history mà allocate không thấy (APH 0.76 tỷ = landmine)."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    adtv_floor_bn = 5.0
    LAM = 7.0
    LIQW = 0.15
    TRAIL_WIN = 60
    TRAIL_X = 0.15

    def allocate(self, feat, w_bench, ctx):
        liq = feat.adtv()
        base = risk_parity(Sigma=downside_cov(feat.returns(252), 252))
        r = feat.returns(120)
        score = 0.5 * momentum_score(r, 120) + 0.5 * downvol_score(r, 120)
        score = (1.0 - self.LIQW) * score + self.LIQW * liquidity_score(liq)
        w = tilt(base, score, 2.0)
        w = w * trailing_stop_gate(feat.closes(), self.TRAIL_WIN, self.TRAIL_X, 0.0)
        s = w.sum()
        w = w / s if s > 0 else base
        return liq_share_cap(w, liq, self.LAM)
'''

ERC_MOM_ER = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, lowvol_score, tilt, er_momentum_score

class ERCMomERStrategy(Strategy):
    """erc_mom_tilt_monthly (nền ERC nghiêng momentum + low-vol) nhưng thay momentum THÔ bằng
    KAUFMAN EFFICIENCY RATIO momentum: momentum được nhân trọng số (0.5 + 0.5·ER) với
    ER = |Δgiá ròng ER_WIN phiên| / Σ|Δ từng phiên| ∈[0,1] — mã trend TĂNG MƯỢT giữ full
    momentum, mã tăng nhờ GIẬT CỤC/nhiễu bị chiết khấu về 50%. Lọc bớt momentum 'ảo'.
     Cải thiện TOÀN DIỆN so với erc_mom thuần: Sharpe/CAGR tăng ở CẢ 10/10 start·cap test,
    MaxDD giữ nguyên (~-45%), và giảm cả độ trễ VNINDEX 2026. VD (start2021 cap0.30):
    Sh 0.77→0.80, CAGR +15.1→+15.9; (start2023): Sh 1.01→1.10, CAGR +19.9→+21.9.
    ER_WIN=20 (Kaufman gốc dùng cửa sổ ngắn 10-20) tốt nhất; 40 tương đương. cap 25-30%.
    ⚠️ Vẫn họ ERC underweight VIC → lag VNINDEX 2026; dòng phòng thủ/DD-thấp."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MOM_WIN = 120
    ER_WIN = 20

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        r = feat.returns(120)
        score = (0.5 * er_momentum_score(feat.closes(), self.MOM_WIN, self.ER_WIN)
                 + 0.5 * lowvol_score(r, 60))
        return tilt(erc, score, 2.0)
'''

SEMI_ERC_MOM_ER = '''\
from app.lab.strategy import Strategy
from app.lab.lib import (risk_parity, downvol_score, tilt, downside_cov,
                         er_momentum_score)

class SemiERCMomERStrategy(Strategy):
    """semi_erc_mom_monthly (nền ERC trên SEMI-covariance nghiêng momentum + downside-vol)
    nhưng thay momentum THÔ bằng KAUFMAN EFFICIENCY RATIO momentum (nhân trọng số 0.5+0.5·ER,
    ER∈[0,1] = độ 'mượt' của xu hướng). Phạt momentum do nhiễu, thưởng trend sạch.
    Phòng thủ kép (semi-cov + lọc trend chất lượng). cap 25-30%.
    ⚠️ Underweight VIC → lag VNINDEX 2026. Muốn DD<30%: + cash overlay (regime_floor=0.0)."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MOM_WIN = 120
    ER_WIN = 20

    def allocate(self, feat, w_bench, ctx):
        base = risk_parity(Sigma=downside_cov(feat.returns(252), 252))
        r = feat.returns(120)
        score = (0.5 * er_momentum_score(feat.closes(), self.MOM_WIN, self.ER_WIN)
                 + 0.5 * downvol_score(r, 120))
        return tilt(base, score, 2.0)
'''

ERC_MOM_ER_V2 = '''\
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, lowvol_score, tilt, er_momentum_score

class ERCMomERv2Strategy(Strategy):
    """ERC + momentum chất lượng (Kaufman ER) — danh mục đa dạng, cân bằng rủi ro,
    nghiêng nhẹ về mã có xu hướng tăng mượt.

    Nền ERC (covariance 252 phiên) → score = 0.7·z(momentum 150 × ER 20) + 0.3·z(ổn
    định giá 60) → weight = ERC × exp(2·score). Rebalance đầu tháng, band 1.5%.
    Khuyến nghị cap 25%. ⚠️ Cửa sổ ER=20 là tham số nhạy."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MOM_WIN = 150
    ER_WIN = 20
    ER_FLOOR = 0.0
    W_MOM = 0.7
    LAM = 2.0

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        score = (self.W_MOM * er_momentum_score(feat.closes(), self.MOM_WIN,
                                                self.ER_WIN, self.ER_FLOOR)
                 + (1.0 - self.W_MOM) * lowvol_score(feat.returns(60), 60))
        return tilt(erc, score, self.LAM)
'''

ERC_MOM_ER_V3 = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, lowvol_score, tilt, er_momentum_score

class ERCMomERv3Strategy(Strategy):
    """ERC + momentum chất lượng (Kaufman ER), CÓ CHẶN BIÊN ĐỘ NGHIÊNG.

    Như erc_mom_er_v2 nhưng kẹp score trong ±SCORE_CAP trước khi nghiêng, nên không
    mã nào bị đẩy sát trần cap. Rebalance đầu tháng, band 1.5%.
    Khuyến nghị cap 25%. ⚠️ Cửa sổ ER=20 là tham số nhạy."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MOM_WIN = 150
    ER_WIN = 20
    ER_FLOOR = 0.0
    W_MOM = 0.7
    LAM = 2.0
    SCORE_CAP = 1.0

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        score = (self.W_MOM * er_momentum_score(feat.closes(), self.MOM_WIN,
                                                self.ER_WIN, self.ER_FLOOR)
                 + (1.0 - self.W_MOM) * lowvol_score(feat.returns(60), 60))
        score = np.clip(score, -self.SCORE_CAP, self.SCORE_CAP)
        return tilt(erc, score, self.LAM)
'''

ERC_MOM_ER_V4 = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, lowvol_score, tilt, er_momentum_score

class ERCMomERv4Strategy(Strategy):
    """ERC + momentum chất lượng, chặn biên độ nghiêng + TRẦN DỊCH CHUYỂN mỗi mã.

    Như v3, thêm move_policy "maxmove": mỗi kỳ không mã nào dịch quá max_move điểm %
    so với tỉ trọng đang nắm. Dùng khi có ràng buộc vận hành về khối lượng lệnh.
    Rebalance đầu tháng. Khuyến nghị cap 25%.

    ⚠️ Trần dịch chuyển là ĐỘ TRỄ, không phải công cụ giảm rủi ro: siết chặt thì
    danh mục chậm bám tín hiệu, đúng lúc cần thoát nhanh lại bị trói.
    ⚠️ Ngoại lệ chủ ý: mã rớt khỏi rổ FTSE bị bán sạch bất kể trần."""
    rebalance_schedule = "monthly"
    move_policy = "maxmove"
    max_move = 0.10
    MOM_WIN = 150
    ER_WIN = 20
    ER_FLOOR = 0.0
    W_MOM = 0.7
    LAM = 2.0
    SCORE_CAP = 1.0

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        score = (self.W_MOM * er_momentum_score(feat.closes(), self.MOM_WIN,
                                                self.ER_WIN, self.ER_FLOOR)
                 + (1.0 - self.W_MOM) * lowvol_score(feat.returns(60), 60))
        score = np.clip(score, -self.SCORE_CAP, self.SCORE_CAP)
        return tilt(erc, score, self.LAM)
'''

ERC_MOM_ER_V5 = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import risk_parity, lowvol_score, tilt, er_momentum_score

class ERCMomERv5Strategy(Strategy):
    """ERC + momentum chất lượng + CASH BẬC THANG theo regime (hợp SDI).

    Composition y hệt v3. Thêm lá chắn tiền mặt: FTSE dưới MA100 và giữ trạng thái
    5 phiên liên tục → giảm còn 50% cổ phiếu. Exposure CHỈ đặt lại tại kỳ rebalance
    tháng (~2-3 lần đổi/năm), giữa kỳ tiền mặt buy-and-hold — user tracking theo
    weight version được. Khuyến nghị cap 25%.

    ⚠️ Metrics GROSS: chưa trừ phí/thuế/trượt giá, cash trong mô phỏng không sinh lời."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.05
    MOM_WIN = 150
    ER_WIN = 20
    ER_FLOOR = 0.0
    W_MOM = 0.7
    LAM = 2.0
    SCORE_CAP = 1.0
    # ── Cash bậc thang theo regime (runner áp; no-look-ahead, trễ 1 phiên) ──
    regime_guard = "ftse_ma"
    regime_ma = 100
    regime_floor = 0.5        # giới hạn SDI: không quá 50% cash
    regime_confirm = 5        # trạng thái giữ 5 phiên mới công nhận (lọc whipsaw)
    regime_step = "rebalance" # đặt exposure ĐÚNG kỳ rebalance tháng, không version khẩn

    def allocate(self, feat, w_bench, ctx):
        erc = risk_parity(Sigma=feat.cov(252))
        score = (self.W_MOM * er_momentum_score(feat.closes(), self.MOM_WIN,
                                                self.ER_WIN, self.ER_FLOOR)
                 + (1.0 - self.W_MOM) * lowvol_score(feat.returns(60), 60))
        score = np.clip(score, -self.SCORE_CAP, self.SCORE_CAP)
        return tilt(erc, score, self.LAM)
'''

MOM_ER_LIQSHARE = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import (lowvol_score, tilt, er_momentum_score, liq_share_cap,
                         cap_weights)

class MomERLiqShareStrategy(Strategy):
    """Momentum chất lượng CÔ ĐẶC + trần thanh khoản — 5-7 mã dẫn dắt, luôn ~100%
    cổ phiếu.

    score = 0.65·z(momentum 150 × ER 20) + 0.35·z(ổn định giá 60) → weight ∝ exp(16·score)
    (rất cô đặc) → trần kép lặp tới hội tụ: mỗi mã ≤ 30% và ≤ 9 × tỉ trọng thanh khoản
    của mã trong rổ; tự loại mã ADTV < 5 tỷ/phiên. Rebalance đầu tháng. Cap nên đặt 30%.

    ⚠️ 5-7 mã nên rủi ro sự kiện đơn lẻ cao, TE ~15%. Phải lặp CẢ HAI trần trong
    allocate: áp một lượt thì bước cap của engine sẽ dồn phần vượt vào mã kém thanh khoản."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    adtv_floor_bn = 5.0
    MOM_WIN = 150
    ER_WIN = 20
    W_MOM = 0.65
    LV_WIN = 60
    LAM = 16.0
    LIQ_LAM = 9.0
    CAPW = 0.30

    def allocate(self, feat, w_bench, ctx):
        liq = feat.adtv()
        anchor = np.ones(feat.n) / feat.n
        score = (self.W_MOM * er_momentum_score(feat.closes(), self.MOM_WIN,
                                                self.ER_WIN, 0.0)
                 + (1.0 - self.W_MOM) * lowvol_score(feat.returns(self.LV_WIN),
                                                     self.LV_WIN))
        w = tilt(anchor, score, self.LAM)
        for _ in range(10):
            w = cap_weights(w, self.CAPW)
            w = liq_share_cap(w, liq, self.LIQ_LAM)
        return w
'''

GATE_BETA_GUARD = '''\
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, downvol_score, lowbeta_score, tilt
import numpy as np

class GateBetaGuardStrategy(Strategy):
    """Composition gate_beta_v2 (3 factor 0.3 mom / 0.3 downvol / 0.4 low-beta +
    per-stock trend gate MA150 ×0.1, tilt λ=3.0) + OVERLAY MARKET-TIMING TIỀN MẶT:
    khi FTSE index < MA200 → giảm gross exposure về regime_floor (phần còn lại cash,
    return 0). No-look-ahead (signal trễ 1 phiên).
    ⚠️ HIỆN regime_floor = 0.9 → khi risk-off vẫn giữ 90% đầu tư (chỉ ~4% thời gian ở
    cash) ⇒ overlay GẦN NHƯ TẮT: MaxDD ~-37/-40% (≈ gate_beta_v2 không overlay),
    Sharpe ~1.2-1.5, CAGR ~+24-31%. ĐỂ CẮT DRAWDOWN thực sự hạ regime_floor: 0.0 =
    full cash khi risk-off → MaxDD ~-18/-19% Sharpe ~1.5-1.8; 0.3 = giữ 30% → DD ~-21%,
    mượt hơn ít whipsaw. Là chiến lược market-timing nên TE vs FTSE cao. cap 25-35%."""
    rebalance_schedule = "monthly"
    move_policy = "band"
    band = 0.015
    MIN_GAP = 15
    MAX_WEIGHT_TRIGGER = 0.20
    GATE_WIN = 150
    GATE_LOW = 0.1
    # ── Regime cash overlay (runner áp) ──
    regime_guard = "ftse_ma"
    regime_ma = 200
    regime_floor = 0.9

    def should_rebalance(self, ctx):
        if ctx.days_since_rebal < self.MIN_GAP:
            return False
        if ctx.is_scheduled:
            return True
        return ctx.max_weight > self.MAX_WEIGHT_TRIGGER

    def allocate(self, feat, w_bench, ctx):
        cl = feat.closes()
        ma = cl[-self.GATE_WIN:].mean(axis=0)
        gate = np.where(cl[-1] > ma, 1.0, self.GATE_LOW)
        r = feat.returns(120)
        score = (0.3 * momentum_score(r, 120) + 0.3 * downvol_score(r, 120)
                 + 0.4 * lowbeta_score(r, 120))
        return tilt(w_bench, score * gate, 3.0)
'''

MA20_LEADERS_BULL = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import momentum_score, trailing_stop_gate, liq_share_cap

class MA20LeadersBullStrategy(Strategy):
    """MA20-LEADERS BULL — 5 cổ phiếu dẫn dắt, TẤN CÔNG cho pha thị trường tăng.
    Người dùng tự quyết định vào/ra; chiến lược không tự phòng thủ.

    score = 0.5·z(close/SMA20) + 0.5·z(momentum 120) → top 5, weight nghịch đảo vol 60.
    Rebalance mỗi 5 phiên, band 2%. Trailing stop: rớt >15% từ đỉnh 120 phiên thì cắt
    hẳn, nếu còn <3 mã thì chuyển cắt mềm (×0.3). liq_share_cap λ=7, loại ADTV < 5 tỷ.

    ⚠️ Yếu khi thị trường mean-reversion. 5 mã nên TE rất cao. Khuyến nghị cap 35%."""
    rebalance_schedule = "daily"
    move_policy = "band"
    band = 0.02
    adtv_floor_bn = 5.0
    MA_WIN = 20
    MOM_WIN = 120
    K = 5
    GAP = 5
    WS = 0.5
    TRAIL_WIN = 120
    TRAIL_X = 0.15
    MIN_ALIVE = 3
    LIQ_LAM = 7.0

    def should_rebalance(self, ctx):
        return ctx.days_since_rebal >= self.GAP

    def allocate(self, feat, w_bench, ctx):
        ratio = feat.close() / feat.closes(self.MA_WIN).mean(axis=0)
        sd = np.std(ratio)
        s_short = (ratio - np.mean(ratio)) / sd if sd > 1e-8 else np.zeros_like(ratio)
        s_long = momentum_score(feat.returns(self.MOM_WIN), self.MOM_WIN)
        score = self.WS * s_short + (1.0 - self.WS) * s_long
        k = min(self.K, feat.n)
        idx = np.argsort(score)[-k:]
        w0 = np.zeros(feat.n)
        vol = feat.returns(60)[:, idx].std(axis=0) + 1e-9
        iv = 1.0 / vol
        w0[idx] = iv / iv.sum()
        w = w0 * trailing_stop_gate(feat.closes(), self.TRAIL_WIN, self.TRAIL_X, 0.0)
        if (w > 0).sum() < self.MIN_ALIVE:
            w = w0 * trailing_stop_gate(feat.closes(), self.TRAIL_WIN, self.TRAIL_X, 0.3)
        s = w.sum()
        if s > 0:
            w = w / s
        return liq_share_cap(w, feat.adtv(), self.LIQ_LAM)
'''

MA20_LEADERS_ALLWEATHER = '''\
import numpy as np
from app.lab.strategy import Strategy
from app.lab.lib import trailing_stop_gate, liq_share_cap

class MA20LeadersAllWeatherStrategy(Strategy):
    """MA20-LEADERS ALL-WEATHER — 5 cổ phiếu dẫn dắt TỰ PHÒNG THỦ, dùng được mọi
    thời điểm (không cần người dùng timing thị trường).

    Chọn mã: score = [0.5·z(close/SMA20) + 0.5·z(momentum skip-month)] · gate_MA150,
    top 5, weight nghịch đảo vol 60. Rebalance mỗi 5 phiên, band 2%.
    Rủi ro từng mã: trailing stop 15%/120 phiên (còn <3 mã thì cắt mềm ×0.3),
    liq_share_cap λ=7, loại ADTV < 5 tỷ.
    Cash overlay: exposure = 20% + 40%·(FTSE≥MA20) + 40%·(FTSE≥MA100), đánh giá hàng
    ngày, tín hiệu trễ 1 phiên.

    ⚠️ Lag index khi thị trường mean-reversion mạnh; 5 mã nên TE rất cao. Cap 35%."""
    rebalance_schedule = "daily"
    move_policy = "band"
    band = 0.02
    adtv_floor_bn = 5.0
    MA_WIN = 20
    MOM_WIN = 120
    SKIP_D = 21
    K = 5
    GAP = 5
    WS = 0.5
    GATE_WIN = 150
    GATE_LOW = 0.5
    TRAIL_WIN = 120
    TRAIL_X = 0.15
    MIN_ALIVE = 3
    LIQ_LAM = 7.0
    # ── Regime cash overlay dual-MA (runner áp, no-look-ahead, trễ 1 phiên) ──
    regime_guard = "ftse_ma"
    regime_ma = 20
    regime_ma2 = 100
    regime_floor = 0.2

    def should_rebalance(self, ctx):
        return ctx.days_since_rebal >= self.GAP

    def _z(self, x):
        sd = np.std(x)
        return (x - np.mean(x)) / sd if sd > 1e-8 else np.zeros_like(x)

    def allocate(self, feat, w_bench, ctx):
        cl = feat.closes()
        ratio = feat.close() / cl[-self.MA_WIN:].mean(axis=0)
        s_short = self._z(ratio)
        # skip-month momentum: return từ t-(MOM_WIN+1) tới t-(SKIP_D+1)
        mom = cl[-(self.SKIP_D + 1)] / cl[-(self.MOM_WIN + 1)] - 1.0
        s_long = self._z(mom)
        score = self.WS * s_short + (1.0 - self.WS) * s_long
        ma_own = cl[-self.GATE_WIN:].mean(axis=0)
        score = score * np.where(cl[-1] > ma_own, 1.0, self.GATE_LOW)
        k = min(self.K, feat.n)
        idx = np.argsort(score)[-k:]
        w0 = np.zeros(feat.n)
        vol = feat.returns(60)[:, idx].std(axis=0) + 1e-9
        iv = 1.0 / vol
        w0[idx] = iv / iv.sum()
        w = w0 * trailing_stop_gate(cl, self.TRAIL_WIN, self.TRAIL_X, 0.0)
        if (w > 0).sum() < self.MIN_ALIVE:
            w = w0 * trailing_stop_gate(cl, self.TRAIL_WIN, self.TRAIL_X, 0.3)
        s = w.sum()
        if s > 0:
            w = w / s
        return liq_share_cap(w, feat.adtv(), self.LIQ_LAM)
'''

PRESETS: dict[str, str] = {
    "risk_parity": RISK_PARITY,
    "risk_parity_monthly": RISK_PARITY_MONTHLY,
    "risk_parity_dd": RISK_PARITY_DD,
    "min_var": MIN_VAR,
    "factor_tilt": FACTOR_TILT,
    "mom_downvol_tilt": MOM_DOWNVOL_TILT,
    "erc_mom_tilt_monthly": ERC_MOM_TILT_MONTHLY,
    "erc_mom_tilt_quarterly": ERC_MOM_TILT_QUARTERLY,
    "erc_mom_trail": ERC_MOM_TRAIL,
    "erc_mom_er": ERC_MOM_ER,
    "erc_mom_er_v2": ERC_MOM_ER_V2,
    "erc_mom_er_v3": ERC_MOM_ER_V3,
    "erc_mom_er_v4": ERC_MOM_ER_V4,
    "erc_mom_er_v5": ERC_MOM_ER_V5,
    "mom_er_liqshare": MOM_ER_LIQSHARE,
    "beta_trig": BETA_TRIG,
    "semi_erc_mom_monthly": SEMI_ERC_MOM_MONTHLY,
    "semi_erc_mom_quarterly": SEMI_ERC_MOM_QUARTERLY,
    "semi_erc_mom_trail": SEMI_ERC_MOM_TRAIL,
    "semi_erc_mom_liqshare": SEMI_ERC_MOM_LIQSHARE,
    "semi_erc_mom_er": SEMI_ERC_MOM_ER,
    "gate_beta": GATE_BETA,
    "gate_beta_dd": GATE_BETA_DD,
    "gate_beta_v2": GATE_BETA_V2,
    "gate_beta_guard": GATE_BETA_GUARD,
    "ma20_leaders_bull": MA20_LEADERS_BULL,
    "ma20_leaders_allweather": MA20_LEADERS_ALLWEATHER,
}
