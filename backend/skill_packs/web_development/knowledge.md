# Web 开发领域知识

## 文件创建最佳实践
- 单文件网页：所有 CSS/JS 内联到 HTML，一个 create_and_run_script 即可完成
- 多文件项目：先创建目录结构，再逐个生成文件
- 图片资源：使用 CSS 渐变、SVG 或 emoji 替代外部图片

## 常见陷阱
- write_file 的 content 超过 2000 字符会被 JSON 截断 → 用 create_and_run_script
- macOS 默认没有 node/npm → 纯 HTML/CSS/JS 方案更可靠
- 文件路径使用绝对路径（~/Desktop/xxx），避免相对路径歧义

## 代码模板
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>标题</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, system-ui, sans-serif; }
    </style>
</head>
<body>
    <!-- 内容 -->
    <script>
        // 交互逻辑
    </script>
</body>
</html>
```
