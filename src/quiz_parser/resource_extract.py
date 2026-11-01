from typing import Any, Dict, List, Union
import re

# -------- 原有全部代码保持原样 --------
AUDIO_PREFIX_FOLDER = "audio"
IMAGE_PREFIX_FOLDER = "image"

def _sanitize_identifier(raw_str: str) -> str:
    """
    将原始路径中的 $ [ ] . 等特殊字符替换为下划线，生成安全路径
    只允许字母数字下划线，连续多个符号压缩成单个下划线，去除首尾下划线
    Mac/Linux环境保留斜杠/层级
    """
    # 注意：不再把 / 替换为下划线，保留目录分隔符
    s = re.sub(r"[\$\[\]\.\\\:]+", "_", raw_str)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def collect_resources(root_data: Any, resource_kind: str) -> List[Dict[str, Any]]:
    if resource_kind == "audio":
        target_key = "a"
        prefix_folder = AUDIO_PREFIX_FOLDER
    elif resource_kind == "image":
        target_key = "i"
        prefix_folder = IMAGE_PREFIX_FOLDER
    else:
        raise ValueError(f"unsupported resource_kind: {resource_kind}")
    result: List[Dict[str, Any]] = []

    def walk(node: Any, path_seg: str):
        if isinstance(node, dict):
            # node 就是 i/a 的【父节点】(group或者question dict)
            if target_key in node:
                res_val = node[target_key]
                if res_val is not None:
                    if isinstance(res_val, list):
                        for idx, sub_item in enumerate(res_val):
                            if isinstance(sub_item, dict) and "pd" in sub_item:
                                raw_inner_path = f"{path_seg}.{target_key}[{idx}]"
                                full_raw_path = f"{prefix_folder}/{raw_inner_path}"
                                safe_path = _sanitize_identifier(full_raw_path)
                                item = {
                                    "path": safe_path,
                                    "pd": sub_item["pd"],
                                    "parent_node": node   # ✅直接保存父dict对象引用！
                                }
                                print(f"[QuizParser] found resource safe_path={safe_path}")
                                result.append(item)
                    elif isinstance(res_val, dict) and "pd" in res_val:
                        raw_inner_path = f"{path_seg}.{target_key}"
                        full_raw_path = f"{prefix_folder}/{raw_inner_path}"
                        safe_path = _sanitize_identifier(full_raw_path)
                        item = {
                            "path": safe_path,
                            "pd": res_val["pd"],
                            "parent_node": node   # ✅父节点引用
                        }
                        print(f"[QuizParser] found resource safe_path={safe_path}")
                        result.append(item)

            ty_val = node.get("t")
            if ty_val == "cloze":
                for k, v in node.items():
                    if k == "questions":
                        continue
                    walk(v, f"{path_seg}.{k}")
                return
            for k, v in node.items():
                walk(v, f"{path_seg}.{k}")
        elif isinstance(node, list):
            for idx, elem in enumerate(node):
                walk(elem, f"{path_seg}[{idx}]")

    walk(root_data, "$")
    return result


# ====================== 新增下面这个工具函数 ======================
def compute_image_disk_paths(image_resource_list: List[Dict[str, Any]], yaml_base_dir: str) -> List[Dict[str, Any]]:
    """
    根据 collect_resources 返回的图片扁平资源列表，推导真实磁盘文件路径（纯字符串计算，不访问磁盘IO）
    约定：
        - 图片磁盘目录：与原始YAML文件同级目录下 `image/` (全小写)
        - 文件命名规则：img_加上5位数字补零，列表下标idx，磁盘序号 = idx + 1
          例：idx=0 → img_00001.png ; idx=15 → img_00016.png
    :param image_resource_list: collect_resources(resource_kind="image")输出的图片资源列表
    :param yaml_base_dir: 原始YAML文件所在的目录（不带末尾斜杠）
    :return: 返回新列表，每个元素在原有dict基础上增加 disk_file_path 字段，代表磁盘完整路径
    """
    import os
    out = []
    for idx, item in enumerate(image_resource_list):
        seq = idx + 1
        filename = f"img_{seq:05d}_.png"
        disk_full = os.path.join(yaml_base_dir, "image", filename)
        new_item = {**item, "disk_file_path": disk_full}
        out.append(new_item)
    return out
