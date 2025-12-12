# lithology_plot.py
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.dates as mdates
import numpy as np

def plot_lithology_belt(df, save_path="lithology_belt.png", font=None):
    """
    根据 df["岩性编码"] 绘制岩性剖面带状图，并保存为 PNG 文件。

    参数：
    - df: 包含 “岩性编码” 与 “运行时间-time” 的 DataFrame
    - save_path: 保存文件路径
    - font: 可选字体（若需要中文）

    返回：
    - save_path（字符串）
    """

    plt.figure(figsize=(14, 3))

    # -1 → NaN（透明）
    data = df["岩性编码"].replace(-1, np.nan).values[np.newaxis, :]

    cmap = mpl.cm.viridis.copy()
    cmap.set_bad(color=(0,0,0,0))  # 透明

    im = plt.imshow(
        data,
        aspect="auto",
        cmap=cmap,
        extent=[
            df["运行时间-time"].min(),
            df["运行时间-time"].max(),
            0, 1
        ]
    )

    plt.yticks([])

    # 时间格式
    ax = plt.gca()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator())

    plt.xlabel("时间（小时）", fontproperties=font if font else None)
    plt.title("岩性剖面带状图", fontproperties=font if font else None)

    cbar = plt.colorbar(im, orientation="vertical")
    cbar.set_label("岩性类别：0=软岩，1=中岩，2=硬岩", fontproperties=font if font else None)

    plt.tight_layout()
    plt.savefig(save_path, dpi=200)
    plt.close()

    return save_path
