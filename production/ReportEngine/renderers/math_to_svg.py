"""
LaTeX 数学公式转 SVG 渲染器
使用 matplotlib 将 LaTeX 公式渲染为 SVG 格式，用于 PDF 导出
"""

import io
import re
from pathlib import Path
from typing import Optional
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties
from loguru import logger

# 使用非交互式后端
matplotlib.use('Agg')


class MathToSVG:
    """将 LaTeX 数学公式转换为 SVG 的转换器"""

    def __init__(self, font_size: int = 14, color: str = 'black'):
        """
        初始化公式转换器

        Args:
            font_size: 字体大小（点）
            color: 文字颜色
        """
        self.font_size = font_size
        self.color = color

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        """判断公式中是否包含中日韩文字。"""
        return bool(re.search(r'[\u3400-\u9fff\uf900-\ufaff]', text or ''))

    @staticmethod
    def _cjk_formula_to_plain_text(latex: str) -> str:
        """将以中文说明文字为主的 LaTeX 公式转换为可打印纯文本。"""
        text = re.sub(r'\\text\s*\{([^{}]*)\}', r'\1', latex)
        replacements = {
            r'\approx': '≈',
            r'\times': '×',
            r'\cdot': '·',
            r'\pm': '±',
            r'\leq': '≤',
            r'\geq': '≥',
            r'\neq': '≠',
        }
        for command, symbol in replacements.items():
            text = text.replace(command, symbol)
        return re.sub(r'\s+', ' ', text.replace('{', '').replace('}', '')).strip()

    def convert_to_svg(self, latex: str, display_mode: bool = True) -> Optional[str]:
        """
        将 LaTeX 公式转换为 SVG 字符串

        Args:
            latex: LaTeX 公式字符串（不包含 $$ 或 $ 符号）
            display_mode: True 为显示模式（块级公式），False 为行内模式

        Returns:
            SVG 字符串，如果转换失败则返回 None
        """
        try:
            # 清理 LaTeX 字符串，去除外层定界符，兼容 $...$ / $$...$$ / \\( \\) / \\[ \\]
            latex = (latex or "").strip()
            patterns = [
                r'^\$\$(.*)\$\$$',
                r'^\$(.*)\$$',
                r'^\\\[(.*)\\\]$',
                r'^\\\((.*)\\\)$',
            ]
            for pat in patterns:
                m = re.match(pat, latex, re.DOTALL)
                if m:
                    latex = m.group(1).strip()
                    break
            # 清理控制字符并做常见兼容
            latex = re.sub(r'[\x00-\x1f\x7f]', '', latex)
            latex = latex.replace(r'\\tfrac', r'\\frac').replace(r'\\dfrac', r'\\frac')
            if not latex:
                logger.warning("空的 LaTeX 公式")
                return None

            # matplotlib 的 mathtext 字体不包含中文。对于中文说明型公式，
            # 转成纯文本并使用报告内置的思源宋体，避免 PDF 中出现方框字。
            contains_cjk = self._contains_cjk(latex)
            render_text = self._cjk_formula_to_plain_text(latex) if contains_cjk else f'${latex}$'
            font_properties = None
            if contains_cjk:
                font_path = (
                    Path(__file__).parent
                    / 'assets'
                    / 'fonts'
                    / 'SourceHanSerifSC-Medium.otf'
                )
                if font_path.exists():
                    font_properties = FontProperties(fname=str(font_path))

            # 创建图形
            fig = plt.figure(figsize=(10, 2) if display_mode else (6, 1))
            fig.patch.set_alpha(0)  # 透明背景

            # 渲染 LaTeX
            # 使用 mathtext 进行渲染
            if display_mode:
                # 显示模式：居中，较大字体
                text = fig.text(
                    0.5, 0.5,
                    render_text,
                    fontsize=self.font_size * 1.2,
                    color=self.color,
                    ha='center',
                    va='center',
                    usetex=False,  # 使用 matplotlib 内置的 mathtext 而非完整 LaTeX
                    fontproperties=font_properties,
                )
            else:
                # 行内模式：左对齐，正常字体
                text = fig.text(
                    0.1, 0.5,
                    render_text,
                    fontsize=self.font_size,
                    color=self.color,
                    ha='left',
                    va='center',
                    usetex=False,
                    fontproperties=font_properties,
                )

            # 获取文本边界框
            fig.canvas.draw()
            bbox = text.get_window_extent(renderer=fig.canvas.get_renderer())

            # 转换为英寸（matplotlib 使用的单位）
            bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())

            # 调整图形大小以适应文本，添加边距
            margin = 0.1  # 英寸
            fig.set_size_inches(
                bbox_inches.width + 2 * margin,
                bbox_inches.height + 2 * margin
            )

            # 重新定位文本到中心
            text.set_position((0.5, 0.5))

            # 保存为 SVG
            svg_buffer = io.StringIO()
            plt.savefig(
                svg_buffer,
                format='svg',
                bbox_inches='tight',
                pad_inches=0.1,
                transparent=True,
                dpi=300
            )
            plt.close(fig)

            # 获取 SVG 内容
            svg_content = svg_buffer.getvalue()
            svg_buffer.close()

            return svg_content

        except Exception as e:
            logger.error(f"LaTeX 公式转换失败: {latex[:100]}... 错误: {str(e)}")
            return None

    def convert_inline_to_svg(self, latex: str) -> Optional[str]:
        """
        将行内 LaTeX 公式转换为 SVG

        Args:
            latex: LaTeX 公式字符串

        Returns:
            SVG 字符串，如果转换失败则返回 None
        """
        return self.convert_to_svg(latex, display_mode=False)

    def convert_display_to_svg(self, latex: str) -> Optional[str]:
        """
        将显示模式 LaTeX 公式转换为 SVG

        Args:
            latex: LaTeX 公式字符串

        Returns:
            SVG 字符串，如果转换失败则返回 None
        """
        return self.convert_to_svg(latex, display_mode=True)


def convert_math_block_to_svg(
    latex: str,
    font_size: int = 16,
    color: str = 'black'
) -> Optional[str]:
    """
    便捷函数：将数学公式块转换为 SVG

    Args:
        latex: LaTeX 公式字符串
        font_size: 字体大小
        color: 文字颜色

    Returns:
        SVG 字符串，如果转换失败则返回 None
    """
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_display_to_svg(latex)


def convert_math_inline_to_svg(
    latex: str,
    font_size: int = 14,
    color: str = 'black'
) -> Optional[str]:
    """
    便捷函数：将行内数学公式转换为 SVG

    Args:
        latex: LaTeX 公式字符串
        font_size: 字体大小
        color: 文字颜色

    Returns:
        SVG 字符串，如果转换失败则返回 None
    """
    converter = MathToSVG(font_size=font_size, color=color)
    return converter.convert_inline_to_svg(latex)


if __name__ == "__main__":
    # 测试代码
    import sys

    # 测试公式
    test_formulas = [
        r"E = mc^2",
        r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        r"\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}",
        r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}",
    ]

    converter = MathToSVG(font_size=16)

    for i, formula in enumerate(test_formulas):
        logger.info(f"测试公式 {i+1}: {formula}")
        svg = converter.convert_display_to_svg(formula)
        if svg:
            # 保存到文件
            filename = f"test_math_{i+1}.svg"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(svg)
            logger.info(f"成功保存到 {filename}")
        else:
            logger.error(f"公式 {i+1} 转换失败")

    logger.info("测试完成")
