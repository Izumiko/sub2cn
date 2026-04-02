#!/usr/bin/env python3
import subprocess
import json
import pysubs2
from openai import OpenAI
import os
import re
import argparse

# ================= 配置区域 =================
# 优先读取系统环境变量中的 OPENAI_API_KEY，如果没有则使用备用字符串（请替换为你自己的 API Key）
API_KEY = os.getenv("OPENAI_API_KEY", "sk-apikey")
BASE_URL = "https://api.deepseek.com"
MODEL_NAME = "deepseek-chat"
BATCH_SIZE = 30 
# ============================================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def get_eng_track_id(mkv_file):
    try:
        result = subprocess.run(['mkvmerge', '-J', mkv_file], capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        for track in info.get('tracks', []):
            if track['type'] == 'subtitles' and track['properties'].get('language') == 'eng':
                if 'SubStationAlpha' in track['codec']:
                    return track['id']
        return None
    except FileNotFoundError:
        print("错误: 未找到 mkvmerge 命令，请确保 MKVToolNix 已添加到系统环境变量。")
        exit(1)
    except Exception as e:
        print(f"获取轨道信息失败: {e}")
        return None

def extract_ass(mkv_file, track_id, output_ass):
    print(f"正在提取英文轨道 {track_id} 到 {output_ass}...")
    subprocess.run(['mkvextract', 'tracks', mkv_file, f"{track_id}:{output_ass}"], check=True)

def translate_batch(batch_texts):
    input_text = "\n".join([f"{i}|{text}" for i, text in enumerate(batch_texts)])
    prompt = (
        "你是一个专业的影视字幕翻译。请根据上下文，将以下英文字幕翻译成流畅的地道中文。\n"
        "【严格格式要求】：\n"
        "1. 输入的每行格式为『序号|英文』，你必须原样返回对应的『序号|中文』，一行对应一行，绝对不能漏行或合并行。\n"
        "2. 保留所有如 {\\an8}、{\\i1} 的 ASS 特效标签，放在翻译结果的合理位置。\n"
        "3. 不要输出任何多余的解释、前言或后缀。\n\n"
        f"待翻译字幕：\n{input_text}"
    )
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"API 调用失败: {e}")
        return ""

def make_bilingual_ass(input_ass, output_ass):
    print(f"\n开始解析并批量翻译字幕文件：{input_ass}")
    subs = pysubs2.load(input_ass)
    
    valid_indices = []
    valid_texts = []
    
    for i, line in enumerate(subs):
        if not line.is_comment and line.text.strip():
            valid_indices.append(i)
            valid_texts.append(line.text)

    total_valid = len(valid_texts)
    print(f"共发现 {total_valid} 行有效字幕，将以每批 {BATCH_SIZE} 行进行处理。")

    for i in range(0, total_valid, BATCH_SIZE):
        batch_texts = valid_texts[i : i + BATCH_SIZE]
        batch_indices = valid_indices[i : i + BATCH_SIZE]
        
        print(f"正在翻译第 {i+1} 到 {min(i+BATCH_SIZE, total_valid)} 行...")
        translated_result = translate_batch(batch_texts)
        
        if not translated_result:
            print("本批次翻译失败，保留原文。")
            continue

        translated_lines = {}
        for line in translated_result.split('\n'):
            match = re.match(r"^(\d+)\|(.+)$", line.strip())
            if match:
                idx = int(match.group(1))
                trans_text = match.group(2).strip()
                translated_lines[idx] = trans_text

        for local_idx, real_idx in enumerate(batch_indices):
            original_text = batch_texts[local_idx]
            chinese_text = translated_lines.get(local_idx, original_text)
            
            if chinese_text and chinese_text != original_text:
                subs[real_idx].text = f"{chinese_text}\\N{original_text}"

    subs.save(output_ass)
    print(f"\n双语字幕已成功生成并保存至：{output_ass}")

def main():
    # 1. 设置 argparse 处理命令行输入
    parser = argparse.ArgumentParser(description="自动提取 MKV 英文字幕并使用 AI 翻译为中英双语字幕。")
    parser.add_argument("mkv_file", help="需要处理的 MKV 视频文件路径")
    args = parser.parse_args()

    mkv_file = args.mkv_file

    if not os.path.exists(mkv_file):
        print(f"错误: 找不到文件 '{mkv_file}'")
        return

    # 2. 根据用户要求，生成目标文件名
    base_name = os.path.splitext(mkv_file)[0]
    eng_ass = f"{base_name}_eng.ass"
    bilingual_ass = f"{base_name}.zh-cn.ass" # 修改为 .zh-cn.ass 格式

    # 3. 执行流程
    track_id = get_eng_track_id(mkv_file)
    if track_id is None:
        print("未在 MKV 文件中找到英文 ASS 字幕轨道！")
        return

    if not os.path.exists(eng_ass):
        extract_ass(mkv_file, track_id, eng_ass)
    else:
        print(f"发现已提取的英文字幕 {eng_ass}，直接进入翻译阶段。")

    make_bilingual_ass(eng_ass, bilingual_ass)
    
    # 清理临时提取的纯英文字幕文件（可选，如果想保留可以注释掉这一行）
    if os.path.exists(eng_ass):
        os.remove(eng_ass)

if __name__ == "__main__":
    main()