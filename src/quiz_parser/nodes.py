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
    RETURN_TYPES = ("ANY", "STRING",)
    RETURN_NAMES = ("audio_resource_list", "transcript_text")
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "从试卷YAML提取全部audio(a)资源，输出扁平化资源list[dict]；同时输出带分组标题的音频文字稿"
    def execute(self, yaml_text: str):
        if not yaml_text or not yaml_text.strip():
            return ([], "")
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="audio")

        # 组装文稿文本
        transcript_lines = []
        groups = data.get("groups", [])
        for g in groups:
            gt_title = g.get("gt", "")
            a_node = g.get("a")
            if not a_node or not isinstance(a_node, dict):
                continue
            pd_list = a_node.get("pd", [])
            if not pd_list or not isinstance(pd_list, list):
                continue
            if gt_title:
                transcript_lines.append(f"[{gt_title}]")
            for entry in pd_list:
                sp = entry.get("sp", "")
                txt = entry.get("txt", "")
                if sp and txt:
                    transcript_lines.append(f"{sp}: {txt}")
        transcript_text = "\n".join(transcript_lines)
        return (res_list, transcript_text)

class QuizParseExtractImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "yaml_text": ("STRING", {"multiline": True, "tooltip": "完整试卷YAML文本"}),
            },
            "optional": {
                "trigger": ("*", {"tooltip": "批量文生图，先做TTS再做T2I，此处接到TTS尾部"}),
            }
        }
    # output0: ZIPPED_PROMPT [(pd,)] 只携带正向提示词，用于元组广播给CLIP
    # output1: PATH_LIST 自定义类型，完整path字符串数组，原样透传给保存节点，不广播拆分
    RETURN_TYPES = ("ZIPPED_PROMPT",)
    RETURN_NAMES = ("zipped_prompt", )
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "解析YAML提取图片资源；输出ZIPPED_PROMPT(仅提示词) + PATH_LIST(完整路径数组)"
    def execute(self, yaml_text: str, **kwargs):
        if not yaml_text or not yaml_text.strip():
            # 空资源：两个都返回空列表
            return ([], [])
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="image")
        zipped = []
        # 同一个循环同时组装两份，保证索引严格对齐
        for item in res_list:
            if not isinstance(item, dict):
                continue
            pd = item.get("pd", "")
            zipped.append((pd,))
        return ((zipped), )

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
        return zipped_prompt

NODE_CLASS_MAPPINGS = {
    "QuizParseExtractAudio": QuizParseExtractAudio,
    "QuizParseExtractImage": QuizParseExtractImage,
    "QuizUnzipPrompt": QuizUnzipPrompt,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "QuizParseExtractAudio": "Quiz: Extract Audio Resources",
    "QuizParseExtractImage": "Quiz: Extract Image Resources",
    "QuizUnzipPrompt": "Quiz: Unzip Prompt",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
