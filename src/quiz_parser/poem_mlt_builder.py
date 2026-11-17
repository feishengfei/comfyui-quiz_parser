'''
诗文YAML转Shotcut MLT核心库
支持两种调用模式：
1. 命令行直接运行：python3 poem_mlt_builder_core.py xxx.yaml [--no-backup]
   CLI默认开启备份，生成 *.bak.mlt；--no‑backup 关闭备份直接原地覆盖
2. 被其他Python模块import，调用 run_build(yaml_path: Path, backup_original: bool)

===== 内存工作流程顺序 =====
调用 run_build(yaml_path, backup_original)
    →校验yaml_file_path文件是否存在，不存在抛异常终止，磁盘无任何修改
    →获取yaml所在目录、stem，校验同目录 {stem}.mlt 模板是否存在，不存在抛异常终止
    →读取yaml到内存 poem_data
    →将原始mlt完整加载进 lxml etree DOM(仅内存，磁盘mlt尚未改动)
    →遍历yaml groups：
        对每一个group，计算对应wav相对路径，拿到绝对磁盘路径
        调用get_wav_duration读取wav：
            返回None → 抛RuntimeError，携带group编号+wav路径，直接终止，磁盘完全不动
        读取wav时长、md5，计算帧对齐、mlt时间字符串，构造seg_info
    →内存中全部构建：chain音频producer、image producer(仅推导png路径，不访问磁盘png)
    →内存重置并填充 playlist0(A1音频轨道), playlist1(V1图片轨道), playlist2(V2字幕合并状态机cover/verse/end)
    →内存更新black producer、background playlist、tractor0总时长
    ✅【全部校验、全部XML构建全部内存完成无异常】
        →如果 backup_original=True：复制原始mlt文件另存为 {stem}.bak.mlt
        →将内存etree DOM写回磁盘，原地覆盖原始 {stem}.mlt
如果任意步骤抛出异常：
    不会执行mlt磁盘写入与备份；上层捕获异常做报错处理

约束边界：
1. YAML缺失 / MLT模板缺失 → 抛错终止，不写磁盘、不备份
2. WAV不存在、打开失败、解码失败 → 直接抛错终止，无fallback兜底
3. PNG图片文件完全不校验磁盘，仅字符串推导相对resource路径写入XML，由后续文生图生成磁盘png
4. image目录是否存在不做校验
5. 所有XML修改完全发生内存，最后一步才落地磁盘，失败绝不污染原始mlt
'''

import argparse
import copy
import math
import wave
import hashlib
import shutil
from pathlib import Path
from lxml import etree
import yaml
from datetime import datetime

MARKER_TODO = "TODOSUBTITLE"
FALLBACK_DURATION = 4.0


def _get_fps_from_profile(root) -> tuple[int, int]:
    profile = root.find("./profile")
    if profile is None:
        return (30, 1)
    num = profile.get("frame_rate_num")
    den = profile.get("frame_rate_den")
    try:
        return int(num), int(den)
    except (ValueError, TypeError):
        return (30, 1)


def _ceil_to_frame(raw_sec: float, frame_step: float) -> float:
    frame_num = math.ceil(raw_sec / frame_step)
    return frame_num * frame_step


def _seconds_to_mlt_time(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    rem = total_seconds % 3600
    minutes = int(rem // 60)
    secs = rem % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def _get_wav_duration(wav_file: Path) -> float | None:
    if not wav_file.exists():
        return None
    try:
        with wave.open(str(wav_file), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return None


def _calc_wav_md5(wav_file: Path) -> str | None:
    if not wav_file.exists():
        return None
    try:
        h = hashlib.md5()
        with open(str(wav_file), "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _get_creation_time_str() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _make_property(name: str, value: str):
    elem = etree.Element("property", {"name": name})
    elem.text = value
    return elem


def run_build(yaml_path: Path, backup_original: bool):
    """
    对外暴露高层入口函数
    :param yaml_path: YAML文件绝对路径
    :param backup_original: True=写入前备份原mlt为 *.bak.mlt；False=直接原地覆盖不备份
    :raises FileNotFoundError, RuntimeError: 各类校验失败抛出异常，调用方捕获
    """
    yaml_dir = yaml_path.parent
    stem = yaml_path.stem
    src_mlt_path = yaml_dir / f"{stem}.mlt"

    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML文件不存在: {yaml_path}")
    if not src_mlt_path.exists():
        raise FileNotFoundError(f"MLT模板不存在: {src_mlt_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        poem_data = yaml.safe_load(f)
    groups = poem_data["groups"]

    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(str(src_mlt_path), parser)
    root = tree.getroot()

    fr_num, fr_den = _get_fps_from_profile(root)
    FRAME_STEP = fr_den / fr_num

    example_sub_prod = root.find('.//producer[@id="producer0"]')
    if example_sub_prod is None:
        raise RuntimeError("模板mlt找不到producer0字幕样例")
    filter_list_example = list(example_sub_prod.xpath("./filter"))
    black_prod = root.find('.//producer[@id="black"]')
    bg_pl = root.find('.//playlist[@id="background"]')
    if black_prod is None or bg_pl is None:
        raise RuntimeError("模板缺失black producer或background playlist")

    insert_pos = root.index(bg_pl) + 1

    def _reset_playlist(pid):
        pl = root.find(f'.//playlist[@id="{pid}"]')
        for child in list(pl):
            tag = child.tag
            if tag in ("entry", "blank"):
                pl.remove(child)
        return pl

    pl0 = _reset_playlist("playlist0")
    pl1 = _reset_playlist("playlist1")
    pl2 = _reset_playlist("playlist2")

    chain_nodes = []
    image_producer_nodes = []
    seg_duration_list = []
    group_segments = []

    for group in groups:
        g_id = group["g"]
        g_num = int(g_id.replace("g", ""))
        st = group["st"]
        has_a = "a" in group
        gst_raw = group.get("gst", None)
        wav_rel = f"audio/_groups_{g_num}_a.wav"
        img_idx = g_num + 1
        img_rel = f"image/img_{img_idx:05d}_.png"
        wav_abs = yaml_dir / wav_rel

        seg_duration_raw: float | None = None
        md5_wav: str | None = None
        if has_a:
            dur_raw = _get_wav_duration(wav_abs)
            if dur_raw is None:
                raise RuntimeError(f"group {g_id} 音频读取失败，路径:{wav_abs}，工作流终止")
            seg_duration_raw = dur_raw
            md5_wav = _calc_wav_md5(wav_abs)
        else:
            # group本身没有音频，使用兜底4秒时长，合法场景
            seg_duration_raw = FALLBACK_DURATION

        seg_length_sec = _ceil_to_frame(seg_duration_raw, FRAME_STEP)
        seg_out_sec = seg_length_sec - FRAME_STEP
        seg_duration_list.append(seg_length_sec)

        mlt_length_str = _seconds_to_mlt_time(seg_length_sec)
        mlt_out_str = _seconds_to_mlt_time(seg_out_sec)
        gst_val = gst_raw.strip() if (gst_raw and isinstance(gst_raw, str)) else None

        seg_info = {
            "g_num": g_num,
            "st": st,
            "has_a": has_a,
            "gst": gst_val,
            "wav_rel": wav_rel,
            "img_rel": img_rel,
            "length_sec": seg_length_sec,
            "out_sec": seg_out_sec,
            "mlt_length": mlt_length_str,
            "mlt_out": mlt_out_str,
        }
        group_segments.append(seg_info)

        if has_a:
            cid = f"chain{g_num}"
            chain_elem = etree.Element("chain", attrib={"id": cid, "out": mlt_out_str})
            props_chain = [
                ("length", mlt_length_str),
                ("eof", "pause"),
                ("resource", wav_rel),
                ("mlt_service", "avformat-novalidate"),
                ("meta.media.nb_streams", "1"),
                ("meta.media.0.stream.type", "audio"),
                ("meta.media.0.codec.sample_fmt", "s16"),
                ("meta.media.0.codec.sample_rate", "24000"),
                ("meta.media.0.codec.channels", "1"),
                ("meta.media.0.codec.layout", "mono"),
                ("meta.media.0.codec.name", "pcm_s16le"),
                ("meta.media.0.codec.long_name", "PCM signed 16-bit little-endian"),
                ("meta.media.0.codec.bit_rate", "384000"),
                ("seekable", "1"),
                ("audio_index", "0"),
                ("video_index", "-1"),
                ("creation_time", _get_creation_time_str()),
                ("astream", "0"),
                ("shotcut:skipConvert", "1"),
                ("shotcut:caption", Path(wav_rel).name),
            ]
            for k, v in props_chain:
                chain_elem.append(_make_property(k, v))
            if md5_wav is not None:
                chain_elem.append(_make_property("shotcut:hash", md5_wav))
            chain_nodes.append(chain_elem)

        pid = f"producer{g_num}"
        prod_img = etree.Element("producer", attrib={"id": pid, "out": mlt_out_str})
        props_img = [
            ("length", "04:00:00.000"),
            ("eof", "pause"),
            ("resource", img_rel),
            ("ttl", "1"),
            ("aspect_ratio", "1"),
            ("meta.media.progressive", "1"),
            ("seekable", "1"),
            ("format", "1"),
            ("meta.media.width", "1080"),
            ("meta.media.height", "1920"),
            ("mlt_service", "qimage"),
            ("shotcut:skipConvert", "1"),
            ("shotcut:caption", Path(img_rel).name),
        ]
        for k, v in props_img:
            prod_img.append(_make_property(k, v))
        image_producer_nodes.append(prod_img)

    for c in chain_nodes:
        root.insert(insert_pos, c)
        insert_pos += 1
    for p in image_producer_nodes:
        root.insert(insert_pos, p)
        insert_pos += 1

    # A1 playlist0
    for seg in group_segments:
        entry_attrib = {"in": "00:00:00.000", "out": seg["mlt_out"]}
        e_a = etree.Element("entry", attrib=entry_attrib)
        e_a.set("producer", f"chain{seg['g_num']}")
        pl0.append(e_a)

    # V1 playlist1
    for seg in group_segments:
        entry_attrib = {"in": "00:00:00.000", "out": seg["mlt_out"]}
        e_v1 = etree.Element("entry", attrib=entry_attrib)
        e_v1.set("producer", f"producer{seg['g_num']}")
        pl1.append(e_v1)

    # ========= V2 合并状态机 =========
    v2_chunks = []
    merge_kind = None
    merge_segs = []
    merge_gst = None

    def flush_merge():
        nonlocal merge_kind, merge_segs, merge_gst
        if merge_kind is None or len(merge_segs) == 0:
            return
        sum_len = sum(s["length_sec"] for s in merge_segs)
        total_sec = sum_len - FRAME_STEP
        if merge_kind == "cover":
            v2_chunks.append({"kind": "subtitle", "mode": "cover", "total_sec": total_sec})
        elif merge_kind == "verse":
            v2_chunks.append({"kind": "subtitle", "mode": "verse", "gst": merge_gst, "total_sec": total_sec})
        merge_kind = None
        merge_segs = []
        merge_gst = None

    for seg in group_segments:
        st = seg["st"]
        gst = seg["gst"]
        dur_out_sec = seg["out_sec"]
        if st == "cover":
            if merge_kind != "cover":
                flush_merge()
                merge_kind = "cover"
                merge_segs = [seg]
            else:
                merge_segs.append(seg)
            merge_gst = None
            continue
        if st == "verse":
            if not gst:
                flush_merge()
                v2_chunks.append({"kind": "blank", "total_sec": dur_out_sec})
                continue
            if merge_kind is None:
                merge_kind = "verse"
                merge_segs.append(seg)
                merge_gst = gst
            else:
                if merge_kind == "verse" and merge_gst == gst:
                    merge_segs.append(seg)
                else:
                    flush_merge()
                    merge_kind = "verse"
                    merge_segs.append(seg)
                    merge_gst = gst
            continue
        if st == "end":
            flush_merge()
            v2_chunks.append({"kind": "blank", "total_sec": dur_out_sec})
            continue
        flush_merge()
        v2_chunks.append({"kind": "blank", "total_sec": dur_out_sec})
    flush_merge()

    # 渲染V2
    sub_producer_counter = 0
    global_filter_id = 0
    for ck in v2_chunks:
        total_sec = ck["total_sec"]
        out_str = _seconds_to_mlt_time(total_sec)
        if ck["kind"] == "blank":
            blk = etree.Element("blank", attrib={"length": out_str})
            pl2.append(blk)
        else:
            sp_id = f"sub_prod_auto_{sub_producer_counter}"
            sub_producer_counter += 1
            sub_prod = copy.deepcopy(example_sub_prod)
            sub_prod.set("id", sp_id)
            sub_prod.set("out", "03:59:59.967")
            for bad_prop_name in ("shotcut:hash", "creation_time"):
                bad_nodes = sub_prod.xpath(f'./property[@name="{bad_prop_name}"]')
                for n in bad_nodes:
                    sub_prod.remove(n)
            old_filters = list(sub_prod.xpath("./filter"))
            for f in old_filters:
                sub_prod.remove(f)
            for orig_f in filter_list_example:
                new_f = copy.deepcopy(orig_f)
                new_f.set("id", f"f_{sp_id}_{global_filter_id}")
                global_filter_id += 1
                new_f.set("out", out_str)
                html_prop = new_f.find('.//property[@name="html"]')
                if html_prop is not None and html_prop.text:
                    orig_html = html_prop.text
                    if ck["mode"] == "verse":
                        new_html = orig_html.replace(MARKER_TODO, ck["gst"])
                    else:
                        new_html = orig_html
                    html_prop.text = new_html
                sub_prod.append(new_f)
            root.insert(insert_pos, sub_prod)
            insert_pos += 1
            entry_sub = etree.Element("entry", attrib={"in": "00:00:00.000", "out": out_str})
            entry_sub.set("producer", sp_id)
            pl2.append(entry_sub)

    # black 总时长
    sum_raw = sum(seg_duration_list)
    black_length_sec = _ceil_to_frame(sum_raw, FRAME_STEP)
    black_out_sec = black_length_sec - FRAME_STEP
    black_len_str = _seconds_to_mlt_time(black_length_sec)
    black_out_str = _seconds_to_mlt_time(black_out_sec)

    black_prod.set("out", black_out_str)
    p_len_black = black_prod.find('./property[@name="length"]')
    if p_len_black is not None:
        p_len_black.text = black_len_str

    for child in list(bg_pl):
        bg_pl.remove(child)
    bg_entry = etree.Element("entry", attrib={
        "producer": "black",
        "in": "00:00:00.000",
        "out": black_out_str
    })
    bg_pl.append(bg_entry)

    tractor0 = root.find('.//tractor0')
    if tractor0 is not None:
        tractor0.set("out", black_out_str)

    # ✅全部内存逻辑执行完毕，开始磁盘操作
    if backup_original:
        bak_path = yaml_dir / f"{stem}.bak.mlt"
        shutil.copy2(src_mlt_path, bak_path)
        print(f"[backup] 已备份原始mlt -> {bak_path}")

    tree.write(
        str(src_mlt_path),
        encoding="utf-8",
        pretty_print=True,
        xml_declaration=True
    )
    print(f"✅ 已原地更新MLT: {src_mlt_path}")


def main():
    parser = argparse.ArgumentParser(description="诗文YAML更新Shotcut MLT，CLI默认开启备份 *.bak.mlt")
    parser.add_argument("yaml_files", nargs="+", help="YAML文件路径")
    parser.add_argument("--no-backup", action="store_true", help="关闭备份，直接原地覆盖原始mlt")
    args = parser.parse_args()
    backup_flag = not args.no_backup
    for yf in args.yaml_files:
        ypath = Path(yf).resolve()
        try:
            run_build(ypath, backup_original=backup_flag)
        except Exception as e:
            print(f"❌ 处理失败 {ypath}: {e}")
            raise


if __name__ == "__main__":
    main()
