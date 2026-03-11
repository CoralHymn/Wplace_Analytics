import os
import json


def generate_file_list():
    # --- 1. 处理当前目录下的 JSON 文件 ---
    all_files = os.listdir('.')
    json_files = [
        f for f in all_files
        if f.startswith('wplace_') and f.endswith('.json')
    ]
    # 降序排列，让日期最新的在前
    json_files.sort(reverse=True)

    # 加上 data/ 前缀
    final_list = ["data/" + f for f in json_files]

    # --- 2. 处理指定目录下的 ZIP 文件 ---
    world_dir = r'D:\编程\Wplace\Wplace_Pumpkin\World'

    if os.path.exists(world_dir):
        # 获取该目录下所有文件
        world_files = os.listdir(world_dir)
        # 筛选 .zip 后缀的文件
        zip_files = [
            f for f in world_files
            if f.lower().endswith('.zip')
        ]
        # 排序（可选，保持列表整洁）
        zip_files.sort()

        # 加上 World/ 前缀并附加到列表末尾
        for f in zip_files:
            final_list.append("World/" + f)
    else:
        print(f"警告：目录未找到 {world_dir}")

    # --- 3. 将最终合并的结果写入 file_list.json ---
    try:
        with open('file_list.json', 'w', encoding='utf-8') as f:
            json.dump(final_list, f, ensure_ascii=False, indent=2)

        print(
            f"成功！已统计 {len(json_files)} 个 JSON 文件和 {len(zip_files) if 'zip_files' in locals() else 0} 个 ZIP 文件。")
        print("当前列表：")
        for name in final_list:
            print(f" - {name}")

    except Exception as e:
        print(f"写入失败: {e}")


if __name__ == "__main__":
    generate_file_list()