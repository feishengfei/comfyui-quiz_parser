import yaml
from .resource_extract import collect_resources

class QuizParseExtractAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "yaml_text": ("STRING", {"multiline": True, "tooltip": "完整试卷YAML文本"}),
            }
        }
    RETURN_TYPES = ("ANY",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "从试卷YAML提取全部audio(a)资源，输出扁平化资源list[dict]"
    def execute(self, yaml_text: str):
        if not yaml_text or not yaml_text.strip():
            return ([],)
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="audio")
        return (res_list,)


class QuizParseExtractImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "yaml_text": ("STRING", {"multiline": True, "tooltip": "完整试卷YAML文本"}),
            }
        }
    # output0: ZIPPED_PROMPT [(pd,)] 只携带正向提示词，用于元组广播给CLIP
    # output1: PATH_LIST 自定义类型，完整path字符串数组，原样透传给保存节点，不广播拆分
    RETURN_TYPES = ("ZIPPED_PROMPT", "PATH_LIST")
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "解析YAML提取图片资源；输出ZIPPED_PROMPT(仅提示词) + PATH_LIST(完整路径数组)"
    def execute(self, yaml_text: str):
        if not yaml_text or not yaml_text.strip():
            # 空资源：两个都返回空列表
            return ([], [])
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="image")

        zipped = []
        path_list = []
        # 同一个循环同时组装两份，保证索引严格对齐
        for item in res_list:
            if not isinstance(item, dict):
                continue
            pd = item.get("pd", "")
            p = item.get("path", "")
            zipped.append((pd,))
            path_list.append(p)
        return (zipped, path_list)


class QuizUnzipPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "zipped_prompt": ("ZIPPED_PROMPT", {"tooltip": "QuizParseExtractImage输出，元组仅包含正向提示词"}),
            }
        }
    # tuple现在只有1个元素，RETURN_TYPES只保留一个STRING输出
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("positive",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Util"
    DESCRIPTION = "解包ZIPPED_PROMPT，元组广播输出正向提示词；path从PATH_LIST分支单独走保存节点，不在此节点处理"
    def execute(self, zipped_prompt):
        if not isinstance(zipped_prompt, list):
            return []
        return zipped_prompt


class QuizCustomImageSaver:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "批量IMAGE张量 [N,H,W,C]"}),
                "path_list": ("PATH_LIST", {"tooltip": "QuizParseExtractImage输出的完整路径数组，自定义类型，第三方节点不可接入"}),
                "save_root": ("STRING", {"default": "./output", "multiline": False, "tooltip": "输出根文件夹"}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images_out",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/IO"
    DESCRIPTION = "批量保存图片；按索引配对images与path_list；透传images输出，用作下游trigger，实现先存图片再跑音频"
    def execute(self, images, path_list, save_root):
        from PIL import Image
        import os
        import torch

        # -------- 运行时防御校验 --------
        if not isinstance(path_list, list):
            print("[QuizCustomImageSaver] warn: path_list不是list，跳过保存")
            return (images,)

        batch_size = images.shape[0]
        if batch_size != len(path_list):
            print(f"[QuizCustomImageSaver] warn: 图片数量({batch_size}) != path_list长度({len(path_list)})，跳过保存，避免错乱")
            return (images,)

        if batch_size == 0:
            print("[QuizCustomImageSaver] info: 无图片资源，跳过保存")
            return (images,)

        # 循环逐张保存
        for idx in range(batch_size):
            rel_path = path_list[idx]
            full_path = os.path.join(save_root, rel_path)
            dir_part = os.path.dirname(full_path)
            os.makedirs(dir_part, exist_ok=True)

            tensor_img = images[idx]
            # tensor [H,W,C] 0~1 → PIL
            arr = (tensor_img * 255).clamp(0,255).byte().cpu().numpy()
            pil_img = Image.fromarray(arr)
            pil_img.save(full_path)
            print(f"[QuizCustomImageSaver] saved: {full_path}")

        # 原样透传batch图像张量，给下游做trigger（内存清理 / 音频触发）
        return (images,)


NODE_CLASS_MAPPINGS = {
    "QuizParseExtractAudio": QuizParseExtractAudio,
    "QuizParseExtractImage": QuizParseExtractImage,
    "QuizUnzipPrompt": QuizUnzipPrompt,
    "QuizCustomImageSaver": QuizCustomImageSaver,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "QuizParseExtractAudio": "Quiz: Extract Audio Resources",
    "QuizParseExtractImage": "Quiz: Extract Image Resources",
    "QuizUnzipPrompt": "Quiz: Unzip Prompt",
    "QuizCustomImageSaver": "Quiz: Custom Batch Image Saver",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
