# -*- coding: utf-8 -*-
"""
把教学视频打包进微信小程序分包（满足单包 <= 2MB 硬限制）。
- 把每个源视频压到 W×H（默认 720×404），按"质量优先"策略线性扫 CRF，取首个 <= TARGET_KB 的一档
- 从源视频抽第 1 秒关键帧做封面（裁剪到 W×H，q80）
- 把 player 页从已存在的参考分包（REF_PKG）复制到目标分包 OUT_PKG/pages/player
- 输出目录结构可直接当一个新的 subPackage 用

用法（直接跑即用默认 演唱会小程序 配置；换项目改下面常量或设环境变量）：
  MINIAPP=/path/to/miniapp SRC_DIR=/path/to/src python build_subpkg_video.py
"""
import os
import shutil
import fractions
import av
from PIL import Image

# ---- 可配置：路径（可用环境变量覆盖，方便换项目复用）----
MINIAPP = os.environ.get("MINIAPP", r"D:\workbuddy\Claw\演唱会小程序\miniapp")
SRC_DIR = os.environ.get("SRC_DIR", r"D:\workbuddy\2026-09-06-15-05-46\vivo_src")
# 参考分包（从这里复制 player 四件套到新分包）；新分包名
REF_PKG = "packageVideo"
OUT_PKG = "packageVivo"
# 封面放主包 images/<POSTER_DIR>/（主包页面才能显示封面；分包只放 mp4！）
POSTER_DIR = "vivo"

# PLAN = [(源文件名, 输出mp4名, 标签), ...]  自己改
PLAN = [
    ("vivo_01_lens.mp4", "vivo_lens.mp4", "增距镜头安装"),
    ("vivo_02_transfer.mp4", "vivo_transfer.mp4", "vivo互传"),
]

# ---- 可配置：编码参数 ----
W, H, FPS = 720, 404, 30          # yuv420p 要求 W、H 都必须是偶数！
TARGET_KB = 950                   # 单视频预算（< 2048KB 上限，留余量给封面+player页）
ABR = 96000                       # 音频码率 bps
CRF_LIST = [28, 30, 32, 34, 36, 38, 40, 42]  # 从好画质到差画质依次尝试


def try_one_crf(src, dst_base, crf):
    """转码一档 CRF，返回 (kb, dur, tmp_path)"""
    tmp = dst_base + ".build.mp4"
    if os.path.exists(tmp):
        os.remove(tmp)

    inp = av.open(src)
    iv = inp.streams.video[0]
    ia = inp.streams.audio[0] if inp.streams.audio else None
    sr = ia.codec_context.sample_rate if ia else 44100

    out = av.open(tmp, "w", format="mp4")
    ov = out.add_stream("libx264", rate=FPS)
    ov.width, ov.height, ov.pix_fmt = W, H, "yuv420p"
    ov.options = {"crf": str(crf), "preset": "veryfast", "profile:v": "main"}
    oa = rs = None
    if ia:
        oa = out.add_stream("aac", rate=sr)
        oa.bit_rate = ABR
        rs = av.AudioResampler(format="fltp", layout="stereo", rate=sr)

    v_pts = a_pts = nv = na = 0
    for frame in inp.decode(iv, ia) if ia else inp.decode(iv):
        if isinstance(frame, av.VideoFrame):
            nf = frame.reformat(width=W, height=H, format="yuv420p")
            nf.pts = v_pts
            nf.time_base = fractions.Fraction(1, FPS)
            v_pts += 1
            nv += 1
            for p in ov.encode(nf):
                out.mux(p)
        elif isinstance(frame, av.AudioFrame):
            for af in rs.resample(frame):
                af.pts = a_pts
                af.time_base = fractions.Fraction(1, sr)
                a_pts += af.samples
                na += 1
                for p in oa.encode(af):
                    out.mux(p)

    for p in ov.encode():
        out.mux(p)
    if oa:
        for p in oa.encode():
            out.mux(p)
    out.close()
    inp.close()

    kb = os.path.getsize(tmp) / 1024.0
    dur = nv / float(FPS)
    return kb, dur, tmp


def transcode(src, dst, tag):
    """线性扫 CRF，选 <= TARGET_KB 中画质最好的；都不满足则用最差一档"""
    if os.path.exists(dst):
        os.remove(dst)
    first_under = None  # (crf, kb, dur, tmp_path)
    last = None
    for crf in CRF_LIST:
        kb, dur, tmp = try_one_crf(src, dst, crf)
        print(f"   [{tag}] CRF {crf:2d} -> {kb:7.1f} KB  {dur:.1f}s")
        if first_under is None and kb <= TARGET_KB:
            first_under = (crf, kb, dur, tmp)
        last = (crf, kb, dur, tmp)

    chosen = first_under if first_under is not None else last
    crf, kb, dur, tmp = chosen
    if kb > TARGET_KB:
        print(f"   [{tag}] 警告：即使 CRF{crf} 仍超 {TARGET_KB}KB，将使用 {kb:.1f}KB")
    shutil.move(tmp, dst)

    # 清理其它 .build.mp4 临时文件
    for f in os.listdir(os.path.dirname(dst)):
        if f.endswith(".build.mp4"):
            os.remove(os.path.join(os.path.dirname(dst), f))
    print(f"   [{tag}] 采用 CRF={crf}，{kb:.1f}KB")
    return kb, dur


def make_poster(src, dst):
    inp = av.open(src)
    iv = inp.streams.video[0]
    im = None
    for frame in inp.decode(iv):
        t = float(frame.pts * iv.time_base)
        if t >= 1.0:
            im = frame.reformat(format="rgb24").to_image()
            break
    inp.close()
    if im is None:
        raise RuntimeError("无法抽帧")
    r = 720 / im.size[0]
    im = im.resize((720, int(im.size[1] * r)), Image.LANCZOS)
    if im.size[1] != H:
        y = (im.size[1] - H) // 2
        im = im.crop((0, y, W, y + H))
    im.save(dst, "JPEG", quality=80, optimize=True)
    return os.path.getsize(dst) / 1024.0


def main():
    pkg = os.path.join(MINIAPP, OUT_PKG)
    os.makedirs(os.path.join(pkg, "pages", "player"), exist_ok=True)
    os.makedirs(os.path.join(pkg, "videos"), exist_ok=True)

    # 复制 player 页到新分包（require 相对路径不变）
    src_p = os.path.join(MINIAPP, REF_PKG, "pages", "player")
    dst_p = os.path.join(pkg, "pages", "player")
    for f in ["player.js", "player.json", "player.wxml", "player.wxss"]:
        shutil.copy2(os.path.join(src_p, f), os.path.join(dst_p, f))
    print(f"已复制 player 页 -> {dst_p}")

    # 封面目录：主包 images/<POSTER_DIR>/（主包页面才能显示；分包内不要放封面！）
    poster_dir = os.path.join(MINIAPP, "images", POSTER_DIR)
    os.makedirs(poster_dir, exist_ok=True)

    out = []
    for src_name, dst_name, tag in PLAN:
        src = os.path.join(SRC_DIR, src_name)
        dst = os.path.join(pkg, "videos", dst_name)
        kb, dur = transcode(src, dst, tag)
        poster = os.path.join(poster_dir, dst_name.replace(".mp4", "_poster.jpg"))
        pkb = make_poster(src, poster)
        print(f"   [{tag}] 封面 -> 主包 {poster}  {pkb:.1f}KB")
        out.append((dst_name, kb, dur, os.path.basename(poster), pkb))

    vid_total = sum(x[1] for x in out)
    poster_total = sum(x[4] for x in out)
    print("\n=== 分包构建完成 ===")
    for name, kb, dur, pname, pkb in out:
        print(f"  {name}  视频 {kb:.1f}KB  封面(主包) {pkb:.1f}KB  {dur:.1f}s")
    print(f"  分包内视频合计 {vid_total:.1f}KB / 分包上限 2048KB（封面已挪主包，不占分包额度）")
    print(f"  主包新增封面 {poster_total:.1f}KB -> {poster_dir}")
    print(f"  分包目录: {pkg}")
    print("  后续: app.json 加 subPackages 项; preloadRule 总和须 <=2MB（一次只预载一个分包）;")
    print("        courses.js 里 videoUrl 指向分包、poster 指向 /images/<POSTER_DIR>/xxx_poster.jpg")


if __name__ == "__main__":
    main()
