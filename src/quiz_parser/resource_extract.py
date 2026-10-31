from typing import Any, Dict, List, Union
import re

# 目录前缀常量，所有业务方统一导入此处，保证路径一致
AUDIO_PREFIX_FOLDER = "audio"
IMAGE_PREFIX_FOLDER = "img"


def _sanitize_identifier(raw_str: str) -> str:
    """
    将原始路径中的 $ [ ] . 等特殊字符替换为下划线，生成安全文件名id
    只允许字母数字下划线，连续多个符号压缩成单个下划线，去除首尾下划线
    """
    s = re.sub(r"[\$\[\]\.\/\\\:]+", "_", raw_str)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def collect_resources(root_data: Any, resource_kind: str) -> List[Dict[str, Any]]:
    """
    递归遍历试卷YAML解析后的数据，收集 a(audio) / i(image) 资源
    :param root_data: yaml safe_load 返回的对象
    :param resource_kind: "audio" | "image"
    :return: 资源对象列表
        [
            {
                "path":str,        # 带prefix_folder原始完整路径，仅调试日志，不可直接做文件名
                "safe_id":str,     # 清洗完毕，用于下游通配匹配 {safe_id}*
                "pd": Any          # 原始pd原样透传
            },
            ...
        ]
    """
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
            # 判断当前dict是否为目标资源节点 a / i
            if target_key in node:
                res_val = node[target_key]
                if res_val is not None and "pd" in res_val:
                    raw_inner_path = f"{path_seg}.{target_key}"
                    # 将prefix_folder并入path
                    full_raw_path = f"{prefix_folder}/{raw_inner_path}"
                    safe_id = _sanitize_identifier(full_raw_path)
                    item = {
                        "path": full_raw_path,
                        "safe_id": safe_id,
                        "pd": res_val["pd"],
                    }
                    print(f"[QuizParser] found resource path={full_raw_path}, safe_id={safe_id}")
                    result.append(item)

            # cloze 题型特殊规则：q数组内部不再递归扫描资源，只扫描group顶层
            ty_val = node.get("ty")
            if ty_val == "cloze":
                for k, v in node.items():
                    if k == "q":
                        continue
                    walk(v, f"{path_seg}.{k}")
                return

            # 普通dict递归全部子key
            for k, v in node.items():
                walk(v, f"{path_seg}.{k}")

        elif isinstance(node, list):
            for idx, elem in enumerate(node):
                walk(elem, f"{path_seg}[{idx}]")

    walk(root_data, "$")
    return result
