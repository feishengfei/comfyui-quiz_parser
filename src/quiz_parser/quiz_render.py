#!/usr/bin/env python3
"""
quiz_render.py
输入 quiz.yaml，生成：
- student.pdf 学生打印卷(A4，无答案无解析无音频)
- teacher.pdf 教师打印卷(A4，小题旁标注答案，无音频)
- interactive.html 单文件交互式试卷(图片音频全部base64内嵌)
依赖：pyyaml, jinja2, playwright
复用同项目 resource_extract.py
"""
import os
import base64
import argparse
import yaml
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from resource_extract import collect_resources, compute_image_disk_paths

# ========== PDF A4打印常量 ==========
PDF_PAGE_FORMAT = "A4"
PDF_MARGIN_TOP = "15mm"
PDF_MARGIN_BOTTOM = "15mm"
PDF_MARGIN_LEFT = "15mm"
PDF_MARGIN_RIGHT = "15mm"
# ====================================

# 脚本自身所在目录（模板j2文件存放于此）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def read_file_as_b64(file_path: str, mime_type: str) -> str:
    """读取二进制文件返回 base64 data‑url字符串"""
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode("utf‑8")
    return f"data:{mime_type};base64,{b64}"

def load_asset_maps(yaml_base_dir: str):
    """
    加载image/audio资源，构建映射字典
    返回: img_map: {logic_safe_path: base64_dataurl}, audio_map: {logic_safe_path: base64_dataurl}
    """
    image_dir = os.path.join(yaml_base_dir, "image")
    audio_dir = os.path.join(yaml_base_dir, "audio")

    yaml_path = os.path.join(yaml_base_dir, "quiz.yaml")
    with open(yaml_path, "r", encoding="utf‑8") as f:
        root_data = yaml.safe_load(f)

    img_raw_list = collect_resources(root_data, resource_kind="image")
    img_resolved = compute_image_disk_paths(img_raw_list, yaml_base_dir)
    img_map = {}
    for item in img_resolved:
        logic_path = item["path"]
        disk_path = item["disk_file_path"]
        if os.path.exists(disk_path):
            img_map[logic_path] = read_file_as_b64(disk_path, "image/png")

    audio_raw_list = collect_resources(root_data, resource_kind="audio")
    audio_map = {}
    for item in audio_raw_list:
        logic_path = item["path"]
        disk_wav = os.path.join(audio_dir, f"{os.path.basename(logic_path)}.wav")
        if os.path.exists(disk_wav):
            audio_map[logic_path] = read_file_as_b64(disk_wav, "audio/wav")
    return img_map, audio_map

def render_html(tpl_env, tpl_name: str, context: dict) -> str:
    tpl = tpl_env.get_template(tpl_name)
    return tpl.render(**context)

def html_to_pdf(html_content: str, output_pdf_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        pdf_opts = {
            "format": PDF_PAGE_FORMAT,
            "margin": {
                "top": PDF_MARGIN_TOP,
                "bottom": PDF_MARGIN_BOTTOM,
                "left": PDF_MARGIN_LEFT,
                "right": PDF_MARGIN_RIGHT,
            },
            "print_background": True
        }
        page.pdf(path=output_pdf_path,** pdf_opts)
        browser.close()

def main():
    parser = argparse.ArgumentParser(description="Quiz YAML render: student.pdf / teacher.pdf / interactive.html")
    parser.add_argument("quiz_yaml", help="path to quiz.yaml")
    parser.add_argument("--shuffle", action="store_true", default=False, help="shuffle question order")
    parser.add_argument("--template_dir", default=SCRIPT_DIR, help="jinja2 template folder")
    args = parser.parse_args()

    quiz_yaml_abs = os.path.abspath(args.quiz_yaml)
    yaml_base_dir = os.path.dirname(quiz_yaml_abs)

    with open(quiz_yaml_abs, "r", encoding="utf‑8") as f:
        quiz_data = yaml.safe_load(f)

    img_map, audio_map = load_asset_maps(yaml_base_dir)

    jinja_env = Environment(loader=FileSystemLoader(args.template_dir), autoescape=True)
    ctx = {
        "quiz": quiz_data,
        "img_map": img_map,
        "audio_map": audio_map,
        "shuffle": args.shuffle
    }

    # 1. 交互网页，输出至yaml同级目录
    html_interactive = render_html(jinja_env, "template_interactive.html.j2", ctx)
    out_html_path = os.path.join(yaml_base_dir, "interactive.html")
    with open(out_html_path, "w", encoding="utf‑8") as f:
        f.write(html_interactive)
    print(f"✅ 已生成: {out_html_path}")

    # 2. 学生打印版PDF
    html_student = render_html(jinja_env, "template_student_print.html.j2", ctx)
    pdf_student = os.path.join(yaml_base_dir, "student.pdf")
    html_to_pdf(html_student, pdf_student)
    print(f"✅ 已生成: {pdf_student}")

    # 3. 教师打印版PDF
    html_teacher = render_html(jinja_env, "template_teacher_print.html.j2", ctx)
    pdf_teacher = os.path.join(yaml_base_dir, "teacher.pdf")
    html_to_pdf(html_teacher, pdf_teacher)
    print(f"✅ 已生成: {pdf_teacher}")

if __name__ == "__main__":
    main()
