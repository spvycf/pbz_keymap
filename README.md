# PBZ 手柄按键自定义工具

> 面向玩家的完整发布说明见 [使用说明.md](使用说明.md)。

在浏览器里点选按键，重新生成 `EnhancedInputUserSettings.sav`。

默认目标配置档：**Custom1**，并默认把存档里的当前档切换为 Custom1。

## 运行

需要 Python 3.8+，无第三方依赖。

```bash
cd tools/pbz_keymap
python3 app.py
```

浏览器会自动打开 <http://127.0.0.1:8765>。停止用 `Ctrl+C`。

可选参数：

```bash
python3 app.py --port 9000
```

## 使用

1. 页面默认载入内置模板（本仓库里的那份 `.sav`）。
2. 在顶部标签选择配置档（默认 Custom1）。
3. 每个动作的每个槽位用一个下拉框选择 Xbox 键；右侧显示该动作的原始默认键。
4. 同一动作、当前键相同的多个槽位会合并成一行（例如轻攻击的槽位 2/4/6），
   修改这一行会同步写入这些槽位；把同一动作的不同行改成同一个键时，它们会自动合并。
5. 勾选“生成后把当前档切换为所选配置档”（默认勾选）。
6. 点“生成并下载 .sav”，浏览器会下载 `EnhancedInputUserSettings.sav`。
7. 退出游戏后，用它替换：

```
<Steam 游戏目录>\PBZ\ProjectPBZ\Saved\EnhancedInputUserSettings.sav
```

替换前请先备份原文件。工具不会覆盖你的输入文件。

## 上传自己的存档

如果你已经在游戏里改过按键，点“上传自己的 .sav”，载入你当前的
`EnhancedInputUserSettings.sav`，工具会在你的文件基础上修改，而不是用内置模板。

## 会改什么 / 不会改什么

会改：

- 目标配置档中每条绑定的“当前键”（`Key`）
- 可选：`CurrentProfileIdentifierString`（当前配置档）

不会改：

- 每条绑定的默认键（`DefaultKey`）
- 槽位、其他配置档
- 尾部 `EnhancedPlayerMappableKeyProfile` 对象、显示名
- 任何角色进度文件

## 安全与校验

- 输入文件只读；生成在内存中完成，输出通过浏览器下载。
- 生成前会重算 Keys 数组、Profile 结构、Profiles 数组的 Size。
- 生成后会重新解析输出并自检：
  - 文件可完整解析；
  - 往返序列化字节一致；
  - 目标档改动生效；
  - 其他档位逐条完全一致。
- 自检失败会直接报错，不产出文件。

## 限制

- 仅支持与本模板同结构/同版本的 `EnhancedInputUserSettings.sav`（UE 5.7.4，
  `ProjectPBZ.PBZInputUserSettings`）。其他版本会明确报错。
- 只处理 Xbox 手柄族（`Family = Xbox`）的按键。
- 不处理键盘映射。
- 同一按键绑定多个动作是允许的（如 A 同时用于跳跃与交互），工具只提示不阻止。
- 未运行游戏验证实际输入优先级；只保证文件结构与字段正确。