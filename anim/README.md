# Pure Pursuit と MPC の計算を見せる Manim シーン

- `GifPP` … Pure Pursuit が 0.1 秒ごとに「先の1点 → 点を通る円 → ハンドル角」を計算し直して線を追う様子。右に式と数値。
- `GifMPC` … サンプリング型 MPC が、ハンドルの切り方 21 通りを 2 秒先まで試走 → 点数 → いちばん良い1本の最初の 0.1 秒だけ実行 → 作り直す、をくり返す様子。

式と定数は、チーム KSK が自動運転AIチャレンジ2026 で使った制御と同じです（図の数値はその式で計算した例）。

```bash
pip install manim==0.19.1
manim -r 1280,720 --fps 30 gifs.py GifPP
manim -r 1280,720 --fps 30 gifs.py GifMPC
# GIF にする
ffmpeg -i media/videos/gifs/720p30/GifPP.mp4 -vf "fps=15,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" pp_loop.gif
```
