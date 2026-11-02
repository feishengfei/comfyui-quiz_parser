# Quiz YAML Schema 字段说明（增量更新版，仅新增 TF判断、fill填空，其余原有逻辑完全保留向下兼容）
> 说明：此文档用于交给AI，用来理解YAML中全部简写字段含义；所有字段均为小写，禁止自行新增未定义字段。
## 顶层字段
| 字段 | 类型 | 说明 |
|---|---|---|
| `quiz_meta` | object | 试卷元信息 |
| `quiz_meta.title` | string | 试卷大标题，页面顶部大标题展示 |
| `quiz_meta.subject` | string | 科目，副标题展示 |
| `quiz_meta.version` | string | 模板版本标记，仅用于版本溯源，页面不渲染 |
| `groups` | array[object] | **试卷大题分组数组**，整套试卷核心，每一项代表一大题 |

## Group（大题组，`groups[]`内对象）
| 字段 | 类型 | 说明 |
|---|---|---|
| `g` | string | group唯一短ID，例如 `g0`、`g1`，仅程序内部标识，页面不显示 |
| `gt` | string | **group‑title，大题显示标题**，页面渲染展示的大题中文标题 |
| `t` | string | group题型类型；可选值：`single`普通单选大题 / `cloze`完形填空大题 |
| `gst` | string | **【可选】group‑shared‑text 大题共享文本**。阅读理解完整原文、完形填空完整挖空短文放在此处；仅group级别可用，question下禁止使用gst。使用`> `yaml多行语法保留换行；完形填空使用标记`___1___`、`___2___`标记挖空位置，**挖空顺序必须和下方questions数组顺序一一对应；程序不做编号校验，由出题人保证正确性**。存在gst时，本组question.stem不要再重复粘贴完整篇章，小题只写问题或空编号。 |
| `a` | object | 【可选】**group层级音频对象，只允许挂在group顶层，小题禁止配置a**。听力大题在这里写对话。 |
| `a.pd` | array[object] | audio‑prompt‑data，音频对话脚本数组，多条对话依次播放 |
| `a.pd[].txt` | string | 角色的外文台词文本 |
| `a.pd[].sp` | string | speaker说话人，**只允许固定集合**：`sophie` / `mature_woman` / `alice_woman` / `clint` / `morgan`，每人都会英语、中文、日语、韩语 |
| `a.pd[].gap` | float | 说完本句之后停顿多少秒，如 `0.8`、`1.0` |
| `i` | object / array[object] | 【可选】group顶层图片；单图写对象，多图写数组；**只包含pd字段，不要写磁盘路径** |
| `i.pd` | string | image‑prompt‑data，AI绘图正向提示词，扁平儿童教材插画风格 |
| `questions` | array[object] | 本大题下面所有小题数组 |

## Question 小题对象（`groups[].questions[]`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `q` | string | 小题唯一短ID，例如`q0`、`q1`，程序内部溯源，页面不直接展示 |
| `type` | string | 小题题型：原有`single`普通单选 / `cloze`完形小题；**新增 `tf` 判断正误题 / `fill` 文本填空题** |
| `stem` | string | **题干文本**，展示给学生看的题目内容；当group配置`gst`时，此处不要再粘贴完整阅读/完形篇章；完形小题仅写空标记例如`___1___`，阅读小题仅写提问问句。可以换行。 |
| `i` | object / array[object] | 【可选】小题配图；单图为对象，多图为数组；仅包含`pd`绘图提示词 |
| `o` | array[object] | option选项数组，单选的候选答案；**type=tf / type=fill 时禁止使用本字段** |
| `ka` | string | key‑answer，**标准答案，对应选项k的值，例如"A"/"B"/"C"/"D"**；`type=tf`、`type=fill`不使用此字段。 |
| `tf_correct` | boolean | 【仅type=`tf`必填】判断正误标准答案；`true`=正确(T)，`false`=错误(F)；其他题型禁止出现此字段 |
| `fill_keys` | array[string] | 【仅type=`fill`必填】填空参考答案数组，支持多个可接受正确答案；其他题型禁止出现此字段 |
| `e` | string | explanation，解析文本；交互页面点击「查看解析」弹窗展示；没有解析也必须填写“暂无解析” |

## Option 选项对象（`questions[].o[]`）
| 字段 | 类型 | 说明 |
|---|---|---|
| `k` | string | key，选项标识，大写字母：`A`/`B`/`C`/`D`，简短，不要长字符串 |
| `t` | string | text，选项显示文本，学生看到的选项内容 |

## 重要约束规则（新增约束已合并到本条）
1. **音频约束**：音频`a`**只允许定义在group顶层，question小题下禁止写a字段**；听力内容必须是角色对话，不能朗读题干。
2. **图片约束**：`i`只写`pd`绘图提示词，**绝对不能写本地磁盘文件名、路径**；单图 `i:{pd:"xxx"}`；多图 `i:[ {pd:"xxx"}, {pd:"xxx"} ]`；group级别的图片只在大题头部渲染一次，不会重复出现在每个小题。
3. **speaker约束**：`sp`只能使用规定的7个名字，不允许自定义名字。
4. **gst共享文本约束**
    - `gst`仅group层级，question不允许出现gst字段；
    - 一篇独立阅读/一篇独立完形 = 一个独立group，每个group拥有自己独立gst；
    - gst存放完整原文，小题stem只保留问题或者挖空编号，禁止重复复制整篇篇章；
    - gst为纯文本，**不能放置图片、音频相关内容**；
    - 完形填空：gst内`___1___`、`___2___`挖空序号顺序与下方questions数组顺序一一对应，程序不会校验匹配关系，由出题方保证。
5. **cloze完形填空**：group的`t: cloze`，questions内小题type写`cloze`；**cloze小题允许挂载i图片，不允许挂载a音频**；每个小题必须有独立`e`解析。
6. **选项k约束**：`k`只用大写英文字母A‑F，不要数字、长id；`ka`的值必须完全等于某一个option的k。
7. **tf 判断正误题型约束**
    - `type: tf`，**禁止设置`o`、禁止设置`ka`**；必须填写`tf_correct`（布尔true/false）；必须填写`e`解析；
    - 渲染：页面展示T/F选项，PDF打印`☐T ☐F`勾选框。
8. **fill 文本填空题约束**
    - `type: fill`，**禁止设置`o`、禁止设置`ka`**；必须填写`fill_keys`字符串数组，至少包含1个参考答案；必须填写`e`解析；
    - 题干中可以使用`___`标记填空位置；交互端渲染文本输入框，PDF渲染手写下划线。
9. 禁止自行创造本表格没有列出的字段。

> 使用建议：
> 给AI生成试卷的提示 = 上面这份markdown说明 + 完整的示范YAML，一起粘贴给大模型，让AI严格参照schema输出yaml。

## 变更点摘要（方便你对比更新）
1. `question.type` 枚举增加两个：`tf`、`fill`
2. question新增字段：`tf_correct`（仅tf）、`fill_keys`（仅fill）
3. 增加约束7、约束8，明确两种新题型哪些字段禁止出现（`o`、`ka`）
4. 增加对应yaml样例；原有所有老字段、老示例完全不动，存量YAML可以直接运行。

