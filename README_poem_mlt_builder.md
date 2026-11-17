# poem_mlt_builder.py

> 
> 诗文YAML → Shotcut MLT工程生成工具（V2字幕轨道专项修订版）

## 概述

读取结构化YAML脚本，基于Shotcut导出的mlt模板，自动生成完整MLT项目文件。
专门针对诗文朗读场景，自动处理音频链、图片素材、V1视频轨道，**重点处理V2富文本字幕轨道的块合并、时长对齐**。
输出文件：`{yaml文件名}_auto.mlt`，可直接用Shotcut打开编辑。

## 依赖

```
pip install pyyaml lxml
```

- `pyyaml`：解析输入YAML配置
- `lxml`：读写、修改MLT(XML)工程文件
- 内置库：wave、math、copy、argparse、pathlib、datetime

## 输入文件结构

### 1. YAML配置文件（如`养兰之道_00001_.yaml`）

顶层key：`groups`，数组，每一项代表一个时间片段group。

group字段说明：

| 字段 | 说明 |
| --- | --- |
| `g` | group编号，格式`g0`、`g1` |
| `gt` | 组标题，仅用于阅读，程序不使用 |
| `st` | **片段类型，核心控制字段**：`cover` / `verse` / `end` /其他 |
| `sn` | 序列号，程序不使用 |
| `gst` | verse模式字幕文本；cover/end一般不填 |
| `a` | 音频配置，存在则读取对应wav音频 |
| `i` | 图片提示词，程序**不做AI绘图**，仅读取预先生成好的png图片 |

### 2. MLT模板文件

命名约定：`{yaml_stem}.mlt`，例如`养兰之道_00001_.mlt`

> 
> 模板要求：
> 
> 
> 1. 包含id=`producer0`样例字幕producer，filter1的html富文本中必须包含大写标记字符串：`TODOSUBTITLE`
> 2. 包含playlist0(A1音频)、playlist1(V1视频)、playlist2(V2字幕轨道)
> 3. 包含`black` color producer、`background` playlist、`tractor0`顶层容器

### 3. 素材目录（相对yaml所在目录）

```
audio/
    _groups_{g_num}_a.wav   # 每个group的配音wav
image/
    img_00001_.png ...     # group对应图片
```

## 运行命令

```
# 单个yaml
python3 poem_mlt_builder.py 养兰之道_00001_.yaml

# 支持多个yaml批量处理
python3 poem_mlt_builder.py file1.yaml file2.yaml
```

## 程序整体工作流程

1. 解析yaml，读取全部groups；
2. 加载模板mlt，读取工程profile帧率；
3. 遍历每一个group：
   - 读取对应wav，计算该片段帧对齐时长：`length_sec`（向上ceil对齐帧边界），`out_sec = length_sec - 1帧`
   - 生成chain音频节点（有a字段时）；生成qimage图片producer节点
4. 重置清空A1/V1/V2三个playlist，插入生成好的chain、producer到XML树；
5. **填充A1(音频)、V1(画面视频)轨道：逐片段紧凑排布，无间隙blank**，A1/V1逻辑全程固定不变，不受V2字幕逻辑改动影响；
6. **V2字幕轨道：状态机合并逻辑（核心）**
7. 渲染合并后的v2_chunks到playlist2；
8. 重算背景black总时长，同步tractor总时长；
9. 写出输出mlt工程文件。

## 🎯 V2字幕状态机核心逻辑（重点）

> 
> 时间计算公式（cover / verse合并统一公式）
> 
> 
> - 合并N个seg：`总时长 = sum(所有seg.length_sec) − FRAME_STEP(1帧)`
> - 单段也复用该公式，行为统一。

### st类型行为

1. **`st: cover` 片头封面组**
   - 连续多个相邻`cover`会**合并为单条V2字幕producer**，不会拆分成多条；
   - 字幕html**保留模板内`TODOSUBTITLE`标记文本，不做替换**；
   - 直到遇到非cover（verse/end/其他st）才flush输出这条cover字幕块。
2. **`st: verse` 正文诗文组**
   - 只有存在非空`gst`才会生成字幕；无gst则输出blank；
   - 相邻group且**gst字符串完全相同**则继续收集合并；
   - gst变更 / st类型变更 / gst为空 → flush输出字幕块；
   - 字幕内部：将模板标记`TODOSUBTITLE`替换为`gst`文本；
3. **`st: end` 结尾组**
   - 强制flush当前正在合并的字幕块；
   - V2轨道只输出`<blank>`，**不生成任何字幕producer**。
4. **其他st类型**
   - flush当前合并块，输出blank占位。

> 
> 循环结束后，会自动flush残留未输出的合并chunk。

### MLT内部时间注意点（容易混淆）

1. **图片 qimage producer**
   - `property name="length">04:00:00.000`：静态图片虚拟源时长，固定4小时，不要修改；
   - producer标签属性 `out="xxx"`：该图片实例实际播放截止时间，动态计算。
2. **字幕sub_producer（复制自producer0模板）**
   - `producer/@out="03:59:59.967"`：仅仅是producer资源上限安全大值，**不是字幕实际显示时长**；
   - `filter/@out="out_str"`：✅**字幕真正生效持续时间**，代码动态设置；
   - playlist entry的`out`必须和filter的out保持一致。

## 输出产物说明

- `xxx_auto.mlt`：最终Shotcut工程，V1放图片序列；A1放音频片段；V2放合并后的字幕/blank；
- 素材仍然引用外部`audio/`、`image/`目录，不会把音视频嵌入mlt。

## 已知约束与注意事项

1. 模板mlt中`producer0`的html必须包含大写字符串 `TODOSUBTITLE`，大小写严格匹配；
2. 合并判断：`verse`的gst是**字符串完全相等才合并**，前后空格会影响合并；代码内部已经做`.strip()`；
3. 帧率读取来自mlt的`<profile>`，默认fallback 30fps；
4. wav读取失败会fallback到`FALLBACK_DURATION=4.0`秒；
5. A1/V1轨道永远是逐group紧凑排布，**V2字幕合并只改变V2轨道，不改动A1/V1时序**。

## 调试排查小技巧

出问题优先看输出mlt源码：

1. 看`playlist2`：cover是否合并成**单条entry**，verse同gst是否合并；
2. 核对字幕filter节点的`out`属性，对比playlist entry的`out`，二者必须完全一致；
3. 看`black` producer的length/out，看tractor0的out，确认工程总时长。

## 版本变更记录

### 当前版本修订点

1. 字幕替换逻辑：废弃span正则，改为直接替换标记字符串`TODOSUBTITLE`；
2. 修复多group合并时长bug：统一 `sum(length_sec) − 1帧`，不再累加out_sec；
3. cover连续多group支持合并为单个V2字幕资源；
4. st=end V2只输出blank，无字幕；
5. 修复复制粘贴引入的`utf‑8`非法破折号编码报错；
6. A1、V1原有逻辑完全保留，不受字幕逻辑改动影响。

---

下面是可直接复制保存为 `README.md` 的纯markdown文本版本（去掉上面说明，直接存文件）：

```
# poem_mlt_builder.py
诗文YAML → Shotcut MLT工程生成工具（V2字幕轨道专项修订版）

## 概述
读取结构化YAML脚本，基于Shotcut导出的mlt模板，自动生成完整MLT项目文件。
专门针对诗文朗读场景，自动处理音频chain、图片素材、V1视频轨道，重点处理V2富文本字幕轨道的块合并、时长对齐。
输出文件：`{yaml文件名}_auto.mlt`，可直接用Shotcut打开编辑。

## 依赖
```bash
pip install pyyaml lxml
```

- `pyyaml`：解析输入YAML配置
- `lxml`：读写、修改MLT(XML)工程文件
- 内置库：wave、math、copy、argparse、pathlib、datetime

## 输入文件

### 1. YAML配置文件

顶层key：`groups`，数组，每一项代表一个时间片段group。

group关键字段：

| 字段 | 说明 |
| --- | --- |
| `g` | group编号，格式`g0`、`g1` |
| `gt` | 组标题，仅用于阅读，程序不使用 |
| `st` | 片段类型，核心控制：`cover` / `verse` / `end` /其他 |
| `gst` | verse模式字幕文本；cover/end一般不填 |
| `a` | 音频配置，存在则读取对应wav音频 |
| `i` | 图片提示词，程序不做AI绘图，读取预生成png图片 |

### 2. MLT模板文件

命名约定：`{yaml_stem}.mlt`

模板硬性要求：

1. 包含id=`producer0`样例字幕producer，filter1的html富文本中必须包含大写标记：`TODOSUBTITLE`
2. playlist0(A1音频)、playlist1(V1视频)、playlist2(V2字幕轨道)
3. 包含`black` color producer、`background` playlist、`tractor0`顶层容器

### 3. 素材目录（相对yaml所在目录）

```
audio/
    _groups_{g_num}_a.wav
image/
    img_00001_.png ...
```

## 运行

```
# 单个yaml
python3 poem_mlt_builder.py 养兰之道_00001_.yaml

# 批量多个yaml
python3 poem_mlt_builder.py file1.yaml file2.yaml
```

## 整体流程

1. 解析yaml读取groups；
2. 加载mlt模板，读取工程profile帧率；
3. 遍历group：读取wav，计算帧对齐时长，生成audio chain、image producer；
4. 重置A1/V1/V2 playlist；
5. A1/V1逐片段紧凑排布，无间隙blank，逻辑固定不变；
6. V2使用状态机做字幕块合并；
7. 渲染V2 chunks到playlist2；
8. 更新black背景总时长、tractor总时长；
9. 写出`xxx_auto.mlt`。

## V2字幕状态机核心

> 
> 时长统一公式：合并N个seg `总时长 = sum(seg.length_sec) − FRAME_STEP(1帧)`

### st类型行为

1. **st: cover**

- 连续相邻cover合并为单条V2字幕producer；
- html保留`TODOSUBTITLE`，不替换文本；
- 遇到非cover才flush输出字幕块。

2. **st: verse**

- 非空gst才生成字幕；无gst输出blank；
- 相邻group gst字符串完全相等则继续合并；
- gst变更 / st变更 / gst为空，flush输出；
- 将模板标记`TODOSUBTITLE`替换为gst文本。

3. **st: end**

- flush当前合并块；V2只输出blank，**不生成字幕producer**。

4. **其他st**

- flush合并块，输出blank占位。

> 
> 遍历结束自动flush残留未输出chunk。

### MLT时间区分（重点）

1. qimage图片producer

- `property length="04:00:00.000"`：静态图片虚拟源时长，固定4小时，请勿修改；
- producer标签`out`：图片实例实际播放截止时间，动态计算。

2. 字幕sub_producer

- `producer/@out="03:59:59.967"`：仅资源上限大值，**不是字幕实际时长**；
- `filter/@out="out_str"`：✅字幕真实生效时长，代码动态设置；
- playlist entry的out必须和filter out保持一致。

## 输出

- `xxx_auto.mlt`：Shotcut工程，V1图片序列，A1音频片段，V2合并字幕/blank；
- 外部引用`audio/`、`image/`素材目录。

## 约束与注意

1. html标记`TODOSUBTITLE`大小写严格匹配；
2. verse合并：gst字符串完全相等才合并，代码内部执行strip；
3. 帧率取自mlt profile，fallback 30fps；
4. wav读取失败fallback `FALLBACK_DURATION=4.0`；
5. V2字幕合并**不改动A1/V1时序**。

## 调试排查

1. 查看输出mlt源码，检查playlist2条目；
2. 字幕filter的`out` 和 playlist entry `out` 必须完全一致；
3. 检查black、tractor0的out确认工程总时长。

## 版本修订记录

1. 字幕替换：废弃span正则，改为标记`TODOSUBTITLE`字符串替换；
2. 修复多group合并时长bug：统一 sum(length_sec) − 1帧；
3. cover支持多group合并为单个V2字幕；
4. st=end V2仅blank，不生成字幕；
5. 修复非法破折号导致的utf‑8编码报错；
6. A1/V1原有逻辑完全保留，不受字幕改动影响。

