from pathlib import Path

# =========================================================
# 把一个文件夹里的所有 .py 文件汇总到一个 txt 文件
# 输出格式：
#
# ===== 文件地址: xxx.py =====
# 代码内容...
#
# =========================================================

# 你的项目文件夹路径
ROOT_DIR = r"C:\Users\22923\Desktop\tbm-report\backend\geology_v2"

# 输出 txt 文件
OUTPUT_FILE = "all_python_code.txt"

# 是否递归遍历子文件夹
RECURSIVE = True


def collect_python_files(root_dir, output_file):
    root = Path(root_dir)

    # 查找所有 py 文件
    if RECURSIVE:
        py_files = root.rglob("*.py")
    else:
        py_files = root.glob("*.py")

    with open(output_file, "w", encoding="utf-8") as out:

        for py_file in py_files:

            try:
                # 相对路径
                relative_path = py_file.relative_to(root)

                # 写入文件头
                out.write("\n")
                out.write("=" * 80 + "\n")
                out.write(f"文件地址: {relative_path}\n")
                out.write("=" * 80 + "\n\n")

                # 读取代码
                with open(py_file, "r", encoding="utf-8") as f:
                    code = f.read()

                # 写入代码
                out.write(code)
                out.write("\n\n")

            except Exception as e:
                out.write(f"[读取失败] {py_file}\n")
                out.write(f"错误: {e}\n\n")

    print(f"完成！输出文件: {output_file}")


if __name__ == "__main__":
    collect_python_files(ROOT_DIR, OUTPUT_FILE)