# 视频路线

视频需 ffmpeg/ffprobe 和同一 Python 环境中的 yt-dlp；缺失时报告依赖，仅在当前授权允许时安装。脚本不调用 LLM。

```bash
{python} "{skill_directory}/scripts/analyze_video.py" "<video_url_or_slug>" --title "<title>"
{python} "{skill_directory}/scripts/analyze_video.py" <slug> --next-review-batch
```

可显式传 --slug 复用工作目录；否则从 stage01 解析。已有本地视频可在 work/<slug>/video.mp4 或 downloads/video.* 处理。Bilibili 下载保留 .part 并通过 HTTP Range 续传。

当前实现只做单阶段粗扫：短视频 0.5fps，长视频均匀覆盖全片、总帧数不超过 90，每批最多 5 帧。只读当次命令打印的 review_frames/*.jpg 精确路径，下一批用 --next-review-batch，不扫描整个帧目录或发明细扫模式。

从实际看到的帧提取步骤，不能补出未见操作。选定帧按同编号 frames/frame_NNNN.png 传给 save_images.py，保存后引用打印的 references/video_frame_NNNN.png。缺失音频/文字或稀疏采样影响步骤判断时说明限制，不将截图推断称完整教程转录。

继续 [素材和输出](output-contract.md)；需要实现代码时再读 [脚本生成](code-generation.md)。
