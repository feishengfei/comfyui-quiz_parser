#!/usr/bin/env python3
"""
诗文YAML转Shotcut MLT工具
修复:
1. DOM插入位置错误，chain插入到black与background中间，background被后移
2. sub_prod带入shotcut:hash、creation_time非法属性
3. filter id全局重复冲突
4. bug: Element.remove()不支持多参数解包
"""
import argparse
import copy
import re
import wave
from pathlib import Path
from lxml import etree
import yaml

FALLBACK_DURATION = 4.0
ONE_FRAME = "00:00:00.033"


def seconds_to_mlt_time(total_seconds: float) -> str:
    hours = int(total_seconds // 3600)
    rem = total_seconds % 3600
    minutes = int(rem // 60)
    secs = rem % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def get_wav_duration(wav_file: Path) -> float | None:
    if not wav_file.exists():
        return None
    try:
        with wave.open(str(wav_file), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return None


def make_property(name: str, value: str):
    elem = etree.Element("property", {"name": name})
    elem.text = value
    return elem


def process_single_yaml(yaml_path: Path):
    print(f"==== 开始处理: {yaml_path.name} ====")
    yaml_dir = yaml_path.parent
    stem = yaml_path.stem
    template_mlt_path = yaml_dir / f"{stem}.mlt"
    output_mlt_path = yaml_dir / f"{stem}_auto.mlt"

    if not template_mlt_path.exists():
        raise FileNotFoundError(f"模板MLT不存在: {template_mlt_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        poem_data = yaml.safe_load(f)
    groups = poem_data["groups"]

    parser = etree.XMLParser(remove_blank_text=True)
    try:
        tree = etree.parse(str(template_mlt_path), parser)
    except Exception as e:
        raise RuntimeError(f"MLT模板XML解析失败 {template_mlt_path}: {e}")
    root = tree.getroot()

    example_sub_prod = root.find('.//producer[@id="producer0"]')
    if example_sub_prod is None:
        raise RuntimeError("模板mlt找不到producer0字幕样例")
    filter_list_example = list(example_sub_prod.xpath("./filter"))

    black_prod = root.find('.//producer[@id="black"]')
    bg_pl = root.find('.//playlist[@id="background"]')
    if black_prod is None or bg_pl is None:
        raise RuntimeError("模板缺失black producer或background playlist")

    insert_pos = root.index(bg_pl) + 1

    def reset_playlist(pid):
        pl = root.find(f'.//playlist[@id="{pid}"]')
        for child in list(pl):
            tag = child.tag
            if tag in ("entry", "blank"):
                pl.remove(child)
        return pl

    pl0 = reset_playlist("playlist0")
    pl1 = reset_playlist("playlist1")
    pl2 = reset_playlist("playlist2")

    chain_nodes = []
    image_producer_nodes = []
    current_global_time_sec = 0.0
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

        seg_duration: float
        if has_a:
            dur = get_wav_duration(wav_abs)
            if dur is not None:
                seg_duration = dur
            else:
                print(f"⚠️ group{g_id}: wav读取失败，fallback {FALLBACK_DURATION}s")
                seg_duration = FALLBACK_DURATION
        else:
            seg_duration = FALLBACK_DURATION

        seg_start = current_global_time_sec
        seg_end = current_global_time_sec + seg_duration
        current_global_time_sec = seg_end
        mlt_out_str = seconds_to_mlt_time(seg_duration)
        gst_val = gst_raw.strip() if (gst_raw and isinstance(gst_raw, str)) else None

        seg_info = {
            "g_num": g_num,
            "st": st,
            "has_a": has_a,
            "gst": gst_val,
            "wav_rel": wav_rel,
            "img_rel": img_rel,
            "duration_sec": seg_duration,
            "start_sec": seg_start,
            "end_sec": seg_end,
            "mlt_out": mlt_out_str,
        }
        group_segments.append(seg_info)

        if has_a and get_wav_duration(wav_abs) is not None:
            cid = f"chain{g_num}"
            chain_elem = etree.Element("chain", attrib={"id": cid, "out": mlt_out_str})
            props_chain = [
                ("length", mlt_out_str),
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
                ("astream", "0"),
                ("shotcut:skipConvert", "1"),
                ("shotcut:caption", wav_rel),
            ]
            for k, v in props_chain:
                chain_elem.append(make_property(k, v))
            chain_nodes.append(chain_elem)

        pid = f"producer{g_num}"
        prod_img = etree.Element("producer", attrib={"id": pid, "out": "03:59:59.967"})
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
            ("shotcut:caption", img_rel),
        ]
        for k, v in props_img:
            prod_img.append(make_property(k, v))
        image_producer_nodes.append(prod_img)

    for c in chain_nodes:
        root.insert(insert_pos, c)
        insert_pos += 1
    for p in image_producer_nodes:
        root.insert(insert_pos, p)
        insert_pos += 1

    # A1 playlist0
    total_seg = len(group_segments)
    for idx, seg in enumerate(group_segments):
        entry_attrib = {"in": "00:00:00.000", "out": seg["mlt_out"]}
        if seg["has_a"] and (get_wav_duration(yaml_dir / seg["wav_rel"]) is not None):
            e_a = etree.Element("entry", attrib=entry_attrib)
            e_a.set("producer", f"chain{seg['g_num']}")
            pl0.append(e_a)
        else:
            blk_a = etree.Element("blank", attrib={"length": seg["mlt_out"]})
            pl0.append(blk_a)
        if idx != total_seg - 1:
            pl0.append(etree.Element("blank", attrib={"length": ONE_FRAME}))

    # V1 playlist1
    for idx, seg in enumerate(group_segments):
        entry_attrib = {"in": "00:00:00.000", "out": seg["mlt_out"]}
        e_v1 = etree.Element("entry", attrib=entry_attrib)
        e_v1.set("producer", f"producer{seg['g_num']}")
        pl1.append(e_v1)
        if idx != total_seg - 1:
            pl1.append(etree.Element("blank", attrib={"length": ONE_FRAME}))

    # V2 gst合并
    v2_chunks = []
    merge_chunk = None
    for seg in group_segments:
        st = seg["st"]
        gst = seg["gst"]
        dur_sec = seg["duration_sec"]
        if st != "verse" or not gst:
            if merge_chunk is not None:
                v2_chunks.append({
                    "kind": "subtitle",
                    "gst": merge_chunk["gst"],
                    "total_sec": merge_chunk["total_sec"]
                })
                merge_chunk = None
            v2_chunks.append({"kind": "blank", "total_sec": dur_sec})
            continue
        if merge_chunk is None:
            merge_chunk = {"gst": gst, "total_sec": dur_sec}
        else:
            if merge_chunk["gst"] == gst:
                merge_chunk["total_sec"] += dur_sec
            else:
                v2_chunks.append({
                    "kind": "subtitle",
                    "gst": merge_chunk["gst"],
                    "total_sec": merge_chunk["total_sec"]
                })
                merge_chunk = {"gst": gst, "total_sec": dur_sec}
    if merge_chunk is not None:
        v2_chunks.append({
            "kind": "subtitle",
            "gst": merge_chunk["gst"],
            "total_sec": merge_chunk["total_sec"]
        })

    sub_producer_counter = 0
    global_filter_id = 0
    total_v2_chunk = len(v2_chunks)
    for idx, ck in enumerate(v2_chunks):
        total_sec = ck["total_sec"]
        out_str = seconds_to_mlt_time(total_sec)
        if ck["kind"] == "blank":
            blk = etree.Element("blank", attrib={"length": out_str})
            pl2.append(blk)
        else:
            gst_text = ck["gst"]
            sp_id = f"sub_prod_auto_{sub_producer_counter}"
            sub_producer_counter += 1
            sub_prod = copy.deepcopy(example_sub_prod)
            sub_prod.set("id", sp_id)
            sub_prod.set("out", "03:59:59.967")

            # 删除shotcut运行时属性
            for bad_prop_name in ("shotcut:hash", "creation_time"):
                bad_nodes = sub_prod.xpath(f'./property[@name="{bad_prop_name}"]')
                for n in bad_nodes:
                    sub_prod.remove(n)

            # -----修复：逐个remove，不能*解包-----
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
                    new_html = re.sub(r'(<span[^>]*>).*?(</span>)', rf"\1{gst_text}\2", orig_html, count=1, flags=re.DOTALL)
                    html_prop.text = new_html
                sub_prod.append(new_f)

            root.insert(insert_pos, sub_prod)
            insert_pos += 1
            entry_sub = etree.Element("entry", attrib={"in": "00:00:00.000", "out": out_str})
            entry_sub.set("producer", sp_id)
            pl2.append(entry_sub)
        if idx != total_v2_chunk - 1:
            pl2.append(etree.Element("blank", attrib={"length": ONE_FRAME}))

    # 更新总时长
    total_project_sec = current_global_time_sec
    total_mlt_time = seconds_to_mlt_time(total_project_sec)

    black_prod.set("out", total_mlt_time)
    p_len_black = black_prod.find('./property[@name="length"]')
    if p_len_black is not None:
        p_len_black.text = total_mlt_time

    for child in list(bg_pl):
        bg_pl.remove(child)
    bg_entry = etree.Element("entry", attrib={
        "producer": "black",
        "in": "00:00:00.000",
        "out": total_mlt_time
    })
    bg_pl.append(bg_entry)

    tractor0 = root.find('.//tractor[@id="tractor0"]')
    if tractor0 is not None:
        tractor0.set("out", total_mlt_time)

    tree.write(
        str(output_mlt_path),
        encoding="utf-8",
        pretty_print=True,
        xml_declaration=True
    )
    print(f"✅ 完成输出: {output_mlt_path}\n")


def main():
    parser = argparse.ArgumentParser(description="诗文YAML批量生成Shotcut MLT工程【修复remove多参数bug】")
    parser.add_argument("yaml_files", nargs="+", help="一个或多个yaml文件路径")
    args = parser.parse_args()
    for yf in args.yaml_files:
        ypath = Path(yf).resolve()
        try:
            process_single_yaml(ypath)
        except Exception as e:
            print(f"❌ 处理 {ypath} 失败: {e}\n")


if __name__ == "__main__":
    main()
