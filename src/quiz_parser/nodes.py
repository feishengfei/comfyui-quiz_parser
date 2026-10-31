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

    RETURN_TYPES = ("ANY",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "从试卷YAML提取全部image(i)资源，输出扁平化资源list[dict]"

    def execute(self, yaml_text: str):
        if not yaml_text or not yaml_text.strip():
            return ([],)
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="image")
        return (res_list,)


NODE_CLASS_MAPPINGS = {
    "QuizParseExtractAudio": QuizParseExtractAudio,
    "QuizParseExtractImage": QuizParseExtractImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "QuizParseExtractAudio": "Quiz: Extract Audio Resources",
    "QuizParseExtractImage": "Quiz: Extract Image Resources",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

