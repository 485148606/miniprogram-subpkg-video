# PyAV 18 视频压缩踩坑手册

本分包压缩脚本依赖 PyAV 18（底层 ffmpeg）。PyAV 18 相比旧版 API 改动很大，下面这些是
实际踩过的坑，改脚本前先读。

## 1. `decode()` 用位置参数，不是关键字
```python
# 旧版（已失效）
for frame in inp.decode(video=iv, audio=ia): ...
# PyAV 18 正确：位置参数，可只传视频
for frame in inp.decode(iv, ia) if ia else inp.decode(iv): ...
```

## 2. 音频重采样：用 `AudioResampler`，没有 `frame.reformat`
PyAV 18 删掉了 `AudioFrame.reformat`。必须显式建 resampler，并手动重置 `pts`：
```python
rs = av.AudioResampler(format="fltp", layout="stereo", rate=sr)
for af in rs.resample(frame):
    af.pts = a_pts
    af.time_base = fractions.Fraction(1, sr)
    a_pts += af.samples
    for p in oa.encode(af):
        out.mux(p)
```

## 3. yuv420p 必须偶数宽高
`ov.pix_fmt = "yuv420p"` 时，W 和 H 都必须为偶数。奇数（如 405）→
`avcodec_open2` 报 "Generic error in an external library"。固定用 720×404。

## 4. 视频帧 pts 必须连续且设 time_base
手动设 `nf.pts = v_pts; nf.time_base = Fraction(1, FPS); v_pts += 1`，否则播放无时长/卡顿。

## 5. CRF 选择策略：取"首个 ≤ 预算"的档，而非最小体积
线性扫 `CRF_LIST`（从好画质到差），选**第一个** `kb <= TARGET_KB` 的
（质量最好且达标）；全超则退而用最差一档并告警。不要选"体积最大"的——那是 bug。

## 6. 抽首帧封面
```python
for frame in inp.decode(iv):
    t = float(frame.pts * iv.time_base)
    if t >= 1.0:                      # 跳过黑场/片头，取 1s 后
        im = frame.reformat(format="rgb24").to_image()
        break
```
封面按比例缩到 W 宽，再居中裁到 H 高，存 q80 optimize=True（约 33–35KB）。

## 7. 封面上限
单张封面控制在 ~35KB，N 个视频预留 `34*N` KB，从视频预算里扣掉。

## 8. 运行环境
用隔离 Python：
`C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe`
需装 `av` 与 `Pillow`（在 managed venv 内）。
