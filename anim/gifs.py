"""記事・X 用のループ GIF（横 16:9、ナレーション無し）を Manim で作る。

シーン:
  GifPP   — Pure Pursuit が 0.1 秒ごとに「先の1点 → 円 → ハンドル」を計算し直して線を追う様子。右に式と数値。
  GifMPC  — MPC が 21 通りを 2 秒先まで試走 → 点数 → いちばん良い1本の最初の 0.1 秒だけ実行 → 作り直す、をくり返す様子。
式と定数は提出コードと同じ（PP: submit-2026-07-26-pp-246、MPC: 77465d1f の _mpc_rollout）。図の数値はその式で計算した例。
実行例: manim -r 1280,720 --fps 30 gifs.py GifPP   /   manim -r 1280,720 --fps 30 gifs.py GifMPC
（Manim Community v0.19、フォントは Noto Sans CJK JP。GIF にするときは ffmpeg の palettegen を使う）
"""
import math
import sys
from pathlib import Path

import numpy as np
from manim import (
    DOWN, LEFT, RIGHT, UP, Circle, Create, DashedLine, Dot, FadeIn, Line, MathTex, Polygon, Rectangle,
    RoundedRectangle, Scene, Text, ValueTracker, VGroup, VMobject, always_redraw, config, rate_functions,
)

FONT = 'Noto Sans CJK JP'
WHITE, TEXT2, DIM = '#FFFFFF', '#C9D6E2', '#7F90A3'
KSK, PP, BAD, GOOD, WARN = '#FF8A1F', '#4DA3FF', '#FF4D6A', '#3DDC84', '#FFC24D'
ROAD, EDGE = '#2A333D', '#E8EEF4'


def jp(s, size=32, color=WHITE, weight='BOLD'):
    return Text(s, font=FONT, font_size=size, color=color, weight=weight)


def kart(color, scale=0.42):
    """上向きのカート（原点が車の中心）"""
    body = Polygon([-0.34, -0.5, 0], [0.34, -0.5, 0], [0.3, 0.4, 0], [0, 0.56, 0], [-0.3, 0.4, 0],
                   color='#0A0C0F', fill_color=color, fill_opacity=1, stroke_width=2)
    wheels = VGroup(*[Rectangle(width=0.12, height=0.26, color='#0A0C0F', fill_color='#0A0C0F', fill_opacity=1)
                      .move_to([sx * 0.42, sy, 0]) for sx in (-1, 1) for sy in (-0.3, 0.3)])
    return VGroup(wheels, body).scale(scale)

config.background_color = '#070B10'
MONO = 'Noto Sans Mono CJK JP'


def panel(x0, x1, y0, y1, color='#1F2B38'):
    return RoundedRectangle(corner_radius=0.18, width=x1 - x0, height=y1 - y0, color=color, fill_color='#0B1118',
                            fill_opacity=1, stroke_width=3).move_to([(x0 + x1) / 2, (y0 + y1) / 2, 0])


def mono(s, size=26, color=WHITE):
    return Text(s, font=MONO, font_size=size, color=color, weight='BOLD')


# ---------------------------------------------------------------------------------------------
class GifPP(Scene):
    """Pure Pursuit を 0.1 秒ずつ、ゆっくり回して見せる"""

    def construct(self):
        S = 0.34                      # 1 m = S ユニット
        O = np.array([-6.7, -0.6, 0])   # 世界座標 (前=+x, 左=+y) の原点の画面位置

        def P(x, y):
            return O + np.array([x * S, y * S, 0])

        def line_y(x):                # 走りたい線（ゆるい S 字）
            return 3.0 * math.sin(x / 3.2)

        xs = np.linspace(-0.6, 32.0, 400)
        pts = np.array([[x, line_y(x)] for x in xs])
        seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
        arc_s = np.concatenate([[0], np.cumsum(seg)])

        def point_ahead(x, y, ld):
            i = int(np.argmin(np.hypot(pts[:, 0] - x, pts[:, 1] - y)))
            j = int(np.searchsorted(arc_s, arc_s[i] + ld))
            j = min(j, len(pts) - 1)
            return pts[j]

        # --- シミュレーション（提出版と同じ式。v は一定で見せる）
        v, dt = 6.0, 0.1
        Lw = 1.80 + 0.004 * v * v
        ld = min(max(3.0 + 0.5 * v, 3.0), 10.0)
        x, y, th = 0.0, 0.9, 0.35
        sim = []
        for _ in range(40):
            tx, ty = point_ahead(x, y, ld)
            dx, dy = tx - x, ty - y
            xl = math.cos(th) * dx + math.sin(th) * dy
            yl = -math.sin(th) * dx + math.cos(th) * dy
            d2 = xl * xl + yl * yl
            kap = 2 * yl / max(d2, 1e-6)
            delta = math.atan(kap * Lw)
            sim.append(dict(x=x, y=y, th=th, tx=tx, ty=ty, xl=xl, yl=yl, d=math.sqrt(d2), kap=kap, delta=delta))
            th += v * math.tan(delta) / Lw * dt
            x += v * math.cos(th) * dt
            y += v * math.sin(th) * dt
            if x > 16.5:
                break

        # --- 固定の絵
        left = panel(-6.95, 1.2, -3.6, 3.6, PP)
        right = panel(1.45, 6.95, -3.6, 3.6)
        title = jp('Pure Pursuit：0.1秒ごとに計算し直す', 30, PP)
        title.move_to([-6.7 + title.width / 2, 3.1, 0])
        path = VMobject(color=EDGE, stroke_width=4).set_points_smoothly([P(px, py) for px, py in pts[::8] if px < 23])
        lab_path = jp('走りたい線', 24, DIM).move_to(P(3.0, -4.6))
        self.add(left, right, path, title, lab_path)

        k = ValueTracker(0)

        def cur():
            return sim[min(int(k.get_value()), len(sim) - 1)]

        def world():
            s = cur()
            g = VGroup()
            trail = [P(q['x'], q['y']) for q in sim[:min(int(k.get_value()), len(sim) - 1) + 1]]
            if len(trail) > 1:
                g.add(VMobject(color=PP, stroke_width=5, stroke_opacity=0.55).set_points_as_corners(trail))
            p0, pt = P(s['x'], s['y']), P(s['tx'], s['ty'])
            # 円弧（いまの向きに接し、目標点を通る）
            arc = []
            L = s['d']
            alpha = math.atan2(s['ty'] - s['y'], s['tx'] - s['x']) - s['th']
            s_end = L if abs(alpha) < 1e-4 else L * alpha / math.sin(alpha)
            kk = s['kap']
            for j in range(30):
                u = s_end * j / 29
                if abs(kk) < 1e-5:
                    arc.append(P(s['x'] + u * math.cos(s['th']), s['y'] + u * math.sin(s['th'])))
                else:
                    arc.append(P(s['x'] + (math.sin(s['th'] + kk * u) - math.sin(s['th'])) / kk,
                                 s['y'] - (math.cos(s['th'] + kk * u) - math.cos(s['th'])) / kk))
            g.add(DashedLine(p0, pt, color=WARN, stroke_width=3, dash_length=0.12))
            g.add(VMobject(color='#BFE0FF', stroke_width=7).set_points_as_corners(arc))
            g.add(Dot(pt, radius=0.11, color=PP), Circle(radius=0.22, color=PP, stroke_width=5).move_to(pt))
            car = kart(PP, 0.55).rotate(s['th'] - math.pi / 2).move_to(p0)
            wheel = Line(ORIGIN3, np.array([math.cos(s['th'] + s['delta']), math.sin(s['th'] + s['delta']), 0]) * 0.75,
                         color=WHITE, stroke_width=6).shift(p0)
            g.add(car, wheel)
            return g

        def numbers():
            s = cur()
            n = min(int(k.get_value()), len(sim) - 1) + 1
            rows = VGroup(
                jp(f'くり返し {n:2d} 回目', 30, PP),
                MathTex(r'v = %.1f\ \mathrm{m/s}' % v, font_size=40, color=WHITE),
                MathTex(r'L_d = 3.0 + 0.5v = %.1f\ \mathrm{m}' % ld, font_size=40, color=WHITE),
                MathTex(r'(x,\,y) = (%.2f,\ %+.2f)' % (s['xl'], s['yl']), font_size=40, color=WARN),
                MathTex(r'\kappa = \frac{2y}{d^2} = %+.3f' % s['kap'], font_size=44, color='#BFE0FF'),
                MathTex(r'\delta = \arctan(\kappa L) = %+.1f^\circ' % math.degrees(s['delta']), font_size=44, color=WHITE),
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.32)
            if rows.width > 5.1:
                rows.scale_to_fit_width(5.1)
            rows.move_to([4.2, 0.35, 0])
            return rows

        note = VGroup(jp('(x, y)：車から見た目標点（x 前・y 左）', 20, TEXT2),
                      jp('L = 1.80 + 0.004v²（実測で合わせた車の長さ）', 20, TEXT2)).arrange(DOWN, aligned_edge=LEFT, buff=0.1)
        if note.width > 5.1:
            note.scale_to_fit_width(5.1)
        note.move_to([4.2, -2.95, 0])
        w = always_redraw(world)
        nums = always_redraw(numbers)
        self.add(w, nums, note)
        self.wait(0.6)
        self.play(k.animate.set_value(len(sim) - 1), run_time=len(sim) * 0.22, rate_func=rate_functions.linear)
        self.wait(1.0)


ORIGIN3 = np.array([0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------------------------
def rollout_from(x, y, th, v, d_cmd, prev, ref_x=0.0, H=20, dt=0.1, hold=5):
    """提出版 _mpc_rollout と同じ手順（むだ時間1step → 0.5秒保持 → 後半は PP で線 x=ref_x へ）。y が前方。"""
    st = prev
    tau, rate, wb, wbk = 0.11, 1.047, 1.80, 0.004
    out = []
    for k in range(H):
        if k < 1:
            target = prev
        elif k < 1 + hold:
            target = d_cmd
        else:
            j = min(k + 3, H - 1)
            rx, ry = ref_x, y + v * 0.1 * (j - k + 1)
            ddx, ddy = rx - x, ry - y
            ld = math.hypot(ddx, ddy)
            yl = -math.sin(th) * ddx + math.cos(th) * ddy
            target = max(-0.5236, min(0.5236, math.atan2(2.0 * wb * yl, max(ld * ld, 1e-3))))
        d = (target - st) * (1.0 - math.exp(-dt / tau))
        d = max(-rate * dt, min(rate * dt, d))
        st += d
        L = wb + wbk * v * v
        kap = abs(math.tan(st)) / L
        a = 1.37 - 0.37 - 0.03 * v - 0.068 * v * v * kap
        v = max(v + a * dt, 0.0)
        th += v * math.tan(st) / L * dt
        x += v * math.cos(th) * dt
        y += v * math.sin(th) * dt
        out.append((x, y, v, th, st))
    return out


class GifMPC(Scene):
    """MPC の1サイクル（試走 → 点数 → 選ぶ → 0.1秒だけ実行）と、そのくり返し"""

    def construct(self):
        S = 0.3
        HW = 3.5
        C0 = np.array([-6.2, -0.25, 0])   # 自車の画面位置（前 = 右）
        off = [0.0]
        cands = np.linspace(-0.5236, 0.5236, 21)
        v0, oy0, ov = 7.0, 9.0, 3.0
        th0 = math.pi / 2

        def P(x, y):  # x：右（画面では下）、y：前（画面では右）
            return C0 + np.array([(y - off[0]) * S, -x * S, 0])

        def eval_set(x0, y0, th, v, prev, oy):
            rows = []
            for dc in cands:
                pts = rollout_from(x0, y0, th, v, float(dc), prev)
                e2 = wall = opp = 0.0
                for kk, (px, py, vv, _, _) in enumerate(pts):
                    e2 += px * px
                    clr = HW - abs(px)
                    if clr < 2.2:
                        wall += 200.0 * (2.2 - clr) ** 2
                    t_k = (kk + 1) * 0.1
                    dlon = (oy + ov * t_k) - py
                    o = max(0.0, 1.0 - abs(px) / (2.0 + 0.5 * t_k))
                    if o > 0 and dlon > 0:
                        short = min(4.5 - dlon, 3.0)
                        if short > 0:
                            opp += min(60.0 * o * short * short, 350.0)
                prog = -30.0 * sum(p[2] * 0.1 for p in pts)
                ds = 30.0 * (float(dc) - prev) ** 2
                rows.append(dict(dc=float(dc), pts=pts, bad=(wall > 1.0 or opp > 1.0), J=e2 + wall + opp + ds + prog))
            return rows

        left = panel(-6.95, 0.75, -3.1, 3.1, KSK)
        right = panel(1.0, 6.95, -3.1, 3.1)
        title = jp('MPC：試して、選んで、0.1秒だけ進む', 34, KSK).move_to([-3.1, 3.55, 0])
        road = Rectangle(width=7.6, height=2 * HW * S, stroke_width=0, fill_color=ROAD, fill_opacity=1).move_to(
            [-3.1, C0[1], 0])
        walls = VGroup(Line([-6.9, C0[1] + HW * S, 0], [0.7, C0[1] + HW * S, 0], color=EDGE, stroke_width=4),
                       Line([-6.9, C0[1] - HW * S, 0], [0.7, C0[1] - HW * S, 0], color=EDGE, stroke_width=4))

        def make_refl():
            g = VGroup()
            k0 = math.floor((off[0] - 3.0) / 1.6)
            for kk in range(k0, k0 + 20):
                a, b = kk * 1.6, kk * 1.6 + 0.8
                a, b = max(a, off[0] - 2.2), min(b, off[0] + 22.5)
                if b > a:
                    g.add(Line(P(0, a), P(0, b), color=TEXT2, stroke_width=3))
            return g

        steps = VGroup(*[jp(s, 28, DIM) for s in (
            '① ハンドルの切り方を 21 通り',
            '② それぞれ 2 秒先まで試走（0.1秒×20）',
            '③ 点数 J をつける（壁・前の車は減点）',
            '④ J がいちばん良い1本を選ぶ',
            '⑤ 最初の 0.1 秒だけ実行 → ①へ')]).arrange(DOWN, aligned_edge=LEFT, buff=0.28)
        if steps.width > 5.5:
            steps.scale_to_fit_width(5.5)
        steps.move_to([3.98, 1.35, 0])

        def hi(i):
            return [steps[j].animate.set_color(KSK if j == i else DIM) for j in range(len(steps))]

        refl = make_refl()
        self.add(left, right, road, walls, refl, title, steps)
        ego = kart(KSK, 0.5).rotate(-math.pi / 2).move_to(P(0, 0)).set_z_index(5)
        opp = kart('#A9B4C0', 0.5).rotate(-math.pi / 2).move_to(P(0, oy0)).set_z_index(5)
        self.add(ego, opp)
        rows = eval_set(0.0, 0.0, th0, v0, 0.0, oy0)

        # ① 21 通り
        rays = VGroup(*[Line(P(0, 0.9), P(0, 0.9) + np.array([math.cos(dc * 1.6), math.sin(dc * 1.6), 0]) * 0.9,
                             color=KSK, stroke_width=4) for dc in cands])
        self.play(*hi(0), *[Create(r) for r in rays], run_time=0.9)
        # ② 試走（前半オレンジ・後半青）
        kt = ValueTracker(0)

        def fan():
            n = int(kt.get_value())
            g = VGroup()
            for r in rows:
                q = [P(0, 0)] + [P(p[0], p[1]) for p in r['pts'][:n]]
                if len(q) < 2:
                    continue
                g.add(VMobject(color=KSK, stroke_width=3.5).set_points_as_corners(q[:7]))
                if len(q) > 6:
                    g.add(VMobject(color=PP, stroke_width=3.5).set_points_as_corners(q[6:]))
            return g

        f = always_redraw(fan)
        self.add(f)
        self.play(*hi(1), run_time=0.3)
        self.remove(*rays)
        self.play(kt.animate.set_value(20), run_time=2.0, rate_func=rate_functions.linear)
        f.clear_updaters()
        self.remove(f)

        # ③ 点数（当たる線は赤）と J の棒
        lines = VGroup(*[VMobject(color=BAD if r['bad'] else KSK, stroke_width=3.5).set_points_as_corners(
            [P(0, 0)] + [P(p[0], p[1]) for p in r['pts']]) for r in rows])
        Js = np.array([r['J'] for r in rows])
        lo, hi_ = Js.min(), np.percentile(Js, 85)
        best = int(np.argmin(Js))

        def bars_for(rows_):
            J = np.array([r['J'] for r in rows_])
            b = int(np.argmin(J))
            g = VGroup()
            for i, r in enumerate(rows_):
                h = 0.12 + 1.35 * min(1.0, (r['J'] - lo) / (hi_ - lo + 1e-9))
                g.add(Rectangle(width=0.2, height=h, stroke_width=0, fill_opacity=1,
                                fill_color=GOOD if i == b else (BAD if r['bad'] else '#5B6B7C'))
                      .move_to([1.85 + i * 0.245, -2.75 + h / 2, 0]))
            return g

        bars = bars_for(rows)
        blab = jp('21 本それぞれの J（低いほど良い）', 22, TEXT2).move_to([3.98, -0.72, 0])
        self.play(*hi(2), FadeIn(lines), FadeIn(bars), FadeIn(blab), run_time=0.9)
        self.wait(0.4)
        # ④ 選ぶ
        chosen = VMobject(color=GOOD, stroke_width=9).set_points_as_corners(
            [P(0, 0)] + [P(p[0], p[1]) for p in rows[best]['pts']]).set_z_index(3)
        self.play(*hi(3), Create(chosen), lines.animate.set_stroke(opacity=0.25), run_time=0.9)
        # ⑤ 0.1秒だけ実行 → くり返す（自車についていく）
        first = Line(P(0, 0), P(rows[best]['pts'][0][0], rows[best]['pts'][0][1]), color=WHITE,
                     stroke_width=12).set_z_index(4)
        self.play(*hi(4), Create(first), run_time=0.6)
        self.wait(0.3)
        self.remove(first)
        st = dict(x=0.0, y=0.0, th=th0, v=v0, oy=oy0)
        cnt = jp('作り直し 0 回目（0.0 秒後）', 24, KSK).move_to([-3.1, -2.75, 0]).set_opacity(0)
        for rep in range(26):
            p1 = rows[best]['pts'][0]
            prev = rows[best]['dc']
            dy = p1[1] - st['y']
            st.update(x=p1[0], y=p1[1], th=p1[3], v=p1[2], oy=st['oy'] + ov * 0.1)
            off[0] = st['y']
            rows = eval_set(st['x'], st['y'], st['th'], st['v'], prev, st['oy'])
            best = min(range(21), key=lambda i: rows[i]['J'])
            nl = VGroup(*[VMobject(color=BAD if r['bad'] else KSK, stroke_width=3, stroke_opacity=0.3)
                          .set_points_as_corners([P(st['x'], st['y'])] + [P(p[0], p[1]) for p in r['pts']])
                          for r in rows])
            nc = VMobject(color=GOOD, stroke_width=9).set_points_as_corners(
                [P(st['x'], st['y'])] + [P(p[0], p[1]) for p in rows[best]['pts']]).set_z_index(3)
            ncnt = jp(f'作り直し {rep + 1} 回目（{(rep + 1) / 10:.1f} 秒後）', 24, KSK).move_to([-3.1, -2.75, 0])
            po = P(0, st['oy'])
            self.play(ego.animate.move_to(P(st['x'], st['y'])),
                      opp.animate.move_to(po).set_opacity(1.0 if po[0] > -6.45 else 0.0),
                      refl.animate.shift(LEFT * dy * S),
                      lines.animate.become(nl), chosen.animate.become(nc),
                      bars.animate.become(bars_for(rows)), cnt.animate.become(ncnt),
                      run_time=0.22 if rep > 2 else 0.45, rate_func=rate_functions.linear)
            self.remove(refl)
            refl = make_refl()
            self.add(refl)
            self.bring_to_back(left, right, road, walls, refl)
        self.wait(1.2)
