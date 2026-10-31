from typing import Any, Dict, List, Union

# 目录前缀常量，所有业务方统一导入此处，保证路径一致
AUDIO_PREFIX_FOLDER = "audio"
IMAGE_PREFIX_FOLDER = "img"


def collect_resources(root_data: Any, resource_kind: str) -> List[Dict[str, Any]]:
    """
    递归遍历试卷YAML解析后的数据，收集 a(audio) / i(image) 资源
    :param root_data: yaml safe_load 返回的对象
    :param resource_kind: "audio" | "image"
    :return: 资源对象列表 [{"path":str, "kind":str, "prefix_folder":str, "pd": Any}, ...]
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
                    full_path = f"{path_seg}.{target_key}"
                    item = {
                        "path": full_path,
                        "kind": resource_kind,
                        "prefix_folder": prefix_folder,
                        "pd": res_val["pd"],
                    }
                    print(f"[QuizParser] found resource path={full_path}")
                    result.append(item)

            # cloze 题型特殊规则：q数组内部不再递归扫描资源，只扫描group顶层
            ty_val = node.get("ty")
            if ty_val == "cloze":
                # 只遍历非q字段，跳过q子树
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
