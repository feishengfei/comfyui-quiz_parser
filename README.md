# comfyui-quiz-parser
parse private defind data-structure for image/audio resource generation
> [!NOTE]
> This projected was created with a [cookiecutter](https://github.com/Comfy-Org/cookiecutter-comfy-extension) template. It helps you start writing custom nodes without worrying about the Python setup.
## Quickstart
1. Install [ComfyUI](https://docs.comfy.org/get_started).
1. Install [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager)
1. Look up this extension in ComfyUI-Manager. If you are installing manually, clone this repository under `ComfyUI/custom_nodes`.
1. Restart ComfyUI.

# Features
- Parse quiz YAML, extract audio / image resources
- ComfyUI custom nodes for TTS & text‑to‑image pipeline
- Helper function to compute real disk file path for generated images

## Develop
To install the dev dependencies and pre‑commit (will run the ruff hook), do:
```bash
cd quiz_parser
pip install -e .[dev]
pre-commit install
```

# ComfyUI Quiz Parser
> 用于从约定格式的试卷YAML中，批量提取音频、图片资源，输出扁平化资源列表，对接下游TTS/文生图节点（MLX生态，Mac优先）

## 概述
本项目是一套ComfyUI自定义节点，配套独立资源提取库，专门面向小学英语试卷生成流水线：
1. 上游：输入一份结构化试卷YAML字符串（由前置节点读取文件得到）
2. 解析：递归遍历YAML树，按照题型规则筛选音频资源(`a`)、图片资源(`i`)
3. 输出：资源列表，每个条目包含**逻辑安全路径`path` + 资源数据`pd`**
4. 下游：
   - 音频：使用`path`作为文件名，对接TTS对话生成节点输出wav音频
   - 图片：不再使用`path`作为磁盘文件名；交由ComfyUI原生`SaveImage`批量生成png
5. 生成后的资源文件，后续交给试卷渲染脚本，复用库内工具函数推导真实磁盘路径，打包生成交互式HTML试卷 / 打印版PDF试卷

> ⚠️ 边界说明
> - 仅负责**提取资源**，不做绘图、不做TTS合成；
> - 完形填空(cloze)规则：仅扫描group顶层的`a`/`i`，不会遍历cloze内部小题`q`；
> - 运行环境：MacOS（MLX） / Linux；Windows不做兼容。

## 字段约定（YAML试卷规范）
### 顶层&分组基础缩写
| 缩写 | 全称 | 说明 |
| ---- | ---- | ---- |
| gt | group title | 组标题 |
| g | group | 大题分组数组 |
| t | type | 题型：`single`普通单选 / `cloze`完形填空 |
| q | question | 小题数组 |
| ka | key answer | 正确答案 |
| e | explanation | 题目解析 |
| o | option | 选项 |
| k | key | 选项标记 A/B/C/D |

### 资源节点规范
#### 音频资源 `a`
音频`pd`固定为**对话数组**，支持多角色交替TTS
```yaml
a:
  pd:
    - txt: "What colour is it?"
      sp: child_girl
      gap: 0.7
    - txt: "It is blue."
      sp: child_boy
      gap: 0.9
```
- `txt`：朗读文本（支持中英混排）
- `sp`：speaker 角色名
  - 女性：`sophie`, `en‑mature_woman`, `en‑alice_woman`
  - 男性：`clint`, `morgan`
  - 孩子：`child_girl`, `child_boy`
- `gap`：本段结束后的静音间隔（秒）

#### 图片资源 `i`
图片`pd`直接是**正向提示字符串**，不再嵌套`prompt`子键；支持单图、同题多图数组
```yaml
# 单图
i:
  pd: "red apple, flat cartoon, children textbook illustration, white background"
# 一题多张图片
i:
  - pd: "big elephant, kid illustration"
  - pd: "small mouse, kid illustration"
```

## 节点清单
### 1. Quiz Extract Audio Resources
- 输入：`yaml_str` (STRING)，YAML试卷完整文本
- 输出：`ANY` 资源列表
- 每条资源结构：
```json
{
  "path": "audio/g_0_a",
  "pd": [
    {"txt":"...", "sp":"...", "gap":0.7},
    {"txt":"...", "sp":"...", "gap":0.9}
  ]
}
```
- 规则：只提取`a`节点；cloze小题内部不扫描资源。
> 音频：`path`（清洗后的安全逻辑路径）直接作为输出wav文件的路径前缀。

### 2. Quiz Extract Image Resources
- 输入：`yaml_str` (STRING)，YAML试卷完整文本
- 输出：`ANY` 资源列表
- 每条资源结构：
```json
{
  "path": "img/g_0_q_0_i",
  "pd": "red apple, flat cartoon, children textbook illustration, white background"
}
```
- 规则：只提取`i`节点；cloze小题内部不扫描资源。

> ⚠️ 图片重要区分：
> - `path`：**逻辑溯源路径（用于调试、映射回YAML树位置），不再作为磁盘实际文件名**。
> - 真实磁盘文件名：交由 ComfyUI `SaveImage` 节点自动生成。

## 资源路径约定
### 音频
1. 内置常量前缀：音频默认前缀 `audio`，固化在`resource_extract.py`
2. 路径清洗：自动剔除 `$ . [ ]` 等JSONPath特殊符号，替换为下划线；保留`/`作为目录分隔符
3. `path`清洗后的安全路径，直接供给TTS下游作为wav输出文件名。

### 图片两套路径约定
1. **逻辑路径(path字段)**
    - 代码内部常量 `IMAGE_PREFIX_FOLDER = "img"`，仅用于生成`path`逻辑溯源字符串，**不等于磁盘文件夹名**。
2. **真实磁盘路径（ComfyUI SaveImage输出）**
    - 存放目录：**原始YAML文件同级目录下 `image/`（全小写文件夹名）**
    - 文件命名格式：`img_XXXXX.png`，**5位数字补零**
    - 规则：图片扁平资源列表下标 `idx` → 磁盘序号 = `idx + 1`
      - idx=0 → `img_00001.png`
      - idx=15 → `img_00016.png`
    - 完整示例磁盘路径：`./image/img_00001.png`

### 辅助工具函数 `compute_image_disk_paths()`
> 文件位置：`resource_extract.py`，**当前没有ComfyUI节点调用，供后续试卷渲染CLI脚本使用**。
```python
def compute_image_disk_paths(image_resource_list: List[Dict[str, Any]], yaml_base_dir: str) -> List[Dict[str, Any]]:
```
- 入参
  - `image_resource_list`：`collect_resources(..., resource_kind="image")` 返回的图片扁平资源列表
  - `yaml_base_dir`：原始试卷YAML所在目录字符串（不带末尾分隔符）
- 返回：新的资源列表，每一项在原有`path`、`pd`基础上，增加字段`disk_file_path`，代表图片完整磁盘绝对/相对路径。
- 特性：纯字符串计算，**不做任何磁盘IO读写**。

## 流水线工作流
```
Load YAML File → Quiz Extract Audio Resources → For Loop → TTS Dialog Generate → *.wav

Load YAML File → Quiz Extract Image Resources → ZIPPED_PROMPT → T2I batch → SaveImage → image/img_00001.png ...
```
> ✅ 重要踩坑记录：
> TTS节点的`play`参数会阻塞循环，循环迭代时只会生成第一条音频。解决方案：在过滤列表`filtered_ops`中加入`play`，丢弃该参数，永久关闭自动播放，避免阻塞卡死。

## 文件结构
```
comfyui‑quiz‑parser/
├── nodes.py                # ComfyUI节点注册入口
├── resource_extract.py    # 独立资源提取核心库（可被试卷渲染脚本复用，含compute_image_disk_paths工具函数）
├── pyproject.toml         # 依赖配置
└── README.md              # 本文档
```

## 依赖
- `pyyaml`：YAML解析
- 适配ComfyUI标准节点运行环境

## 测试用YAML
配套两份测试样例：
1. `quiz_demo_2audio.yaml`：多音频测试，验证多条音频提取、循环TTS
2. `quiz_demo_5imgs.yaml`：多图片测试，包含题干单图、一题多图、group顶层图片、cloze分组图片

## 已知限制 & 后续规划
### 当前限制
1. 仅支持`single`单选、`cloze`完形填空两种题型
2. 图片仅支持正向提示词，无负面提示词字段
3. cloze小题`q`内部不支持挂载音频/图片资源，资源只能定义在group顶层
4. 不支持Windows路径兼容

### 后续可扩展
1. 阅读理解题型支持
2. 资源校验节点（检查pd字段完整性）
3. 生成资源清单报告
4. 试卷HTML渲染CLI（复用同一份`resource_extract.py`路径常量 + `compute_image_disk_paths`推导磁盘图片路径，保证路径对齐）

## 排错清单
| 现象 | 原因 | 处理 |
|---|---|---|
| For循环只产出第一条音频，后续卡住 | TTS节点开启play，阻塞等待播放完成 | 将`play`加入`filtered_ops`过滤 |
| No such file or directory | 输出子目录不存在 | 生成文件前取`final_wav.parent.mkdir(parents=True, exist_ok=True)` |
| 提取不到cloze里的图片 | 设计规则：cloze只扫描group顶层 | 将`i`写在group层级，不要写在cloze的q子项 |
| 路径出现`$ [ ]` | 清洗逻辑失效 | 核对`_sanitize_identifier`正则表达式 |
```

### 改动要点总结
1. resource_extract.py：新增`compute_image_disk_paths`，纯计算工具，供将来渲染脚本调用；原有全部提取逻辑不动。
2. README：
   - 明确区分图片「逻辑path」和「真实磁盘路径」两套概念；
   - 写明5位数字补零命名规则、磁盘文件夹名`image/`；
   - 完整记录新增工具函数入参返回、用途；
   - 更新流水线，图片链路写明对接`SaveImage`；
   - 保留音频全部原有文档描述不变。

> 现在没有任何ComfyUI节点调用`compute_image_disk_paths`，完全预留给后面写试卷HTML/PDF渲染CLI使用。
