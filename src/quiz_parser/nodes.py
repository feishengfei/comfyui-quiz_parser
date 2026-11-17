import yaml
from pathlib import Path
from .resource_extract import collect_resources
from .poem_mlt_builder import run_build
class QuizParseExtractAudio:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "yaml_text": ("STRING", {"multiline": True, "tooltip": "完整试卷YAML文本"}),
            }
        }
    RETURN_TYPES = ("ANY", "STRING", "STRING",)
    RETURN_NAMES = ("audio_resource_list", "transcript_text", "tts_plain_text")
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "从试卷YAML提取全部audio(a)资源，输出扁平化资源list[dict]；同时输出带分组标题的音频文字稿；新增tts_plain_text为去掉分组标题、去掉speaker的纯tts台词"
    def execute(self, yaml_text: str):
        if not yaml_text or not yaml_text.strip():
            return ([], "", "")
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="audio")
        # 组装带分组标题+角色的文稿文本
        transcript_lines = []
        # 组装纯tts文本：过滤gt标题，过滤speaker，只取txt
        tts_plain_lines = []
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
                    # 纯tts，只加入txt原文
                    tts_plain_lines.append(txt.strip())
        transcript_text = "\n".join(transcript_lines)
        tts_plain_text = "\n".join(tts_plain_lines)
        return (res_list, transcript_text, tts_plain_text)


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
    RETURN_TYPES = ("ZIPPED_PROMPT",)
    RETURN_NAMES = ("zipped_prompt", )
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Extract"
    DESCRIPTION = "解析YAML提取图片资源；输出ZIPPED_PROMPT(仅提示词)"
    def execute(self, yaml_text: str, **kwargs):
        if not yaml_text or not yaml_text.strip():
            # 无图片，返回空的zipped_prompt元组列表
            return ([], )
        data = yaml.safe_load(yaml_text)
        res_list = collect_resources(data, resource_kind="image")
        zipped = []
        for item in res_list:
            if not isinstance(item, dict):
                continue
            pd = item.get("pd", "")
            zipped.append((pd,))
        return (zipped, )


class QuizUnzipPrompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "zipped_prompt": ("ZIPPED_PROMPT", {"tooltip": "QuizParseExtractImage输出，元组仅包含正向提示词"}),
            }
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("positive",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Util"
    DESCRIPTION = "解包ZIPPED_PROMPT，元组广播输出正向提示词；空输入返回空字符串，下游文生图跳过生成"
    def execute(self, zipped_prompt=None):
        # 防御：输入为空、None直接返回空字符串，不抛出异常
        if zipped_prompt is None or not zipped_prompt:
            return ""
        return zipped_prompt

class PathGetBasename:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": "输入文件路径字符串，输出路径的basename（文件名）"
                }),
            }
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("basename",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Util"
    DESCRIPTION = "输入文件路径字符串，提取返回 basename(文件名，不含目录)"

    def execute(self, file_path: str):
        if not file_path or not file_path.strip():
            return ("", )
        try:
            p = Path(file_path.strip())
            basename_str = p.name
        except Exception:
            basename_str = ""
        return (basename_str,)

class PathGetFileStem:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": "输入文件路径字符串，输出文件stem：去除目录与扩展名，仅主文件名"
                }),
            }
        }
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("stem",)
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Util"
    DESCRIPTION = "输入文件路径字符串，提取stem（剔除目录、文件后缀，仅主文件名）"

    def execute(self, file_path: str):
        if not file_path or not file_path.strip():
            return ("", )
        try:
            p = Path(file_path.strip())
            stem_str = p.stem
        except Exception:
            stem_str = ""
        return (stem_str,)

class PoemMetaParse:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "yaml_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "schema_poem规范YAML文本，解析poem_meta下title、author_or_source、dynasty"
                }),
            }
        }
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("title", "author_or_source", "dynasty", "content")
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Poem"
    DESCRIPTION = "解析schema_poem YAML的poem_meta，输出title, author_or_source, dynasty，缺失字段返回空字符串"

    def execute(self, yaml_text: str):
        title_out = ""
        author_out = ""
        dynasty_out = ""
        content_out = ""
        if not yaml_text or not yaml_text.strip():
            return (title_out, author_out, dynasty_out, content_out)
        try:
            data = yaml.safe_load(yaml_text)
            if isinstance(data, dict):
                meta = data.get("poem_meta", {})
                if isinstance(meta, dict):
                    title_out = meta.get("title", "").strip()
                    author_out = meta.get("author_or_source", "").strip()
                    dynasty_out = meta.get("dynasty", "").strip()
                    content_out = meta.get("content", "").strip()
        except Exception as e:
            print(f"[WARN PoemMetaParse] parse error: {str(e)}")
        return (title_out, author_out, dynasty_out, content_out)

# -------------------- 新增ComfyUI节点类，粘贴到nodes.py的class区 --------------------
class PomMltBuilder:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "trigger": ("BOOLEAN", {"default": False, "tooltip":"上游trigger信号，True才执行本节点逻辑"}),
                "yaml_file_path": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip":"YAML文件绝对路径，同级目录需要存在同名.mlt模板"
                }),
            },
            "optional": {
                "backup_original_mlt": ("BOOLEAN", {"default": False, "tooltip":"是否备份原始mlt为 *.bak.mlt；ComfyUI默认关闭备份，直接原地覆盖"})
            }
        }
    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("trigger_out", )
    FUNCTION = "execute"
    CATEGORY = "QuizParser/Poem"
    DESCRIPTION = "调用poem_mlt_builder_core，根据YAML原地更新Shotcut MLT；仅推导图片路径，图片由下游生成；wav必须预先就绪。"

    def execute(self, trigger: bool, yaml_file_path: str, backup_original_mlt=False):
        if not trigger:
            return (False,)
        if not yaml_file_path or not yaml_file_path.strip():
            raise RuntimeError("yaml_file_path 不能为空")
        p = Path(yaml_file_path.strip()).resolve()
        run_build(p, backup_original=backup_original_mlt)
        return (True,)


NODE_CLASS_MAPPINGS = {
    "QuizParseExtractAudio": QuizParseExtractAudio,
    "QuizParseExtractImage": QuizParseExtractImage,
    "QuizUnzipPrompt": QuizUnzipPrompt,
    "PathGetBasename": PathGetBasename,
    "PathGetFileStem": PathGetFileStem,
    "PoemMetaParse": PoemMetaParse,
    "PomMltBuilder": PomMltBuilder,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "QuizParseExtractAudio": "Quiz: Extract Audio Resources",
    "QuizParseExtractImage": "Quiz: Extract Image Resources",
    "QuizUnzipPrompt": "Quiz: Unzip Prompt",
    "PathGetBasename": "Util: Get Path Basename",
    "PathGetFileStem": "Util: Get Path File Stem",
    "PoemMetaParse": "Poem: Parse poem_meta",
    "PomMltBuilder": "Poem: MLT Builder(Core)",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
