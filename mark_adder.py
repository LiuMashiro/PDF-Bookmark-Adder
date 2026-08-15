import os
import re
from pypdf import PdfReader, PdfWriter


def get_valid_pdf_path():
    """获取并验证用户输入的PDF路径"""
    while True:
        path = input("请拖入PDF或输入PDF文件路径: ").strip()
        #自动去除路径首尾的双引号、单引号
        path = path.strip('"\'')
        if os.path.isfile(path) and path.lower().endswith('.pdf'):
            return path
        print("[错误] 输入错误，请重新输入。")

AI_PROMPT = """将书籍目录提取为「页码-标题」格式（每行一项，回车换行）。
要求：
- 使用plaintext代码块包裹输出
- 使用目录中标注的原始页码，不要做任何偏移或换算；
- 板块、部分、章、节、小节等各层级条目均需逐行列出；
- 层级标记：章、篇、部分、板块、编、卷等大类为一级项，行首不加标记；
  节、小节、本章小结等下属单位为二级项，行首加「...」三个半角点标记；
- 尽量压缩标题，不要太长。
示例：
002-绪论
003-第一章
...003-1.1 概述
...005-1.2 入门
...005-本章小结
007-第二章
...007-2.1 进阶
严禁出现："绪论"而非"002-绪论"等不遵守格式的行\n"""

def copy_to_clipboard(text):
    """将文本写入系统剪贴板"""
    text = str(text) if text is not None else ""

    # 复制
    if os.name == 'nt':
        try:
            if _copy_via_winapi(text):
                return True
        except Exception as e:
            print(f"[警告] Win32 剪贴板写入失败: {e}", file=__import__('sys').stderr)

    # 降级
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.after(50, root.destroy)
        root.mainloop()
        return True
    except Exception as e:
        print(f"[警告] tkinter 剪贴板写入失败: {e}", file=__import__('sys').stderr)
        return False

def _copy_via_winapi(text):
    """通过 ctypes 调用 Windows 剪贴板 API 写入 CF_UNICODETEXT"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE

    if not user32.OpenClipboard(0):
        return False
    try:
        user32.EmptyClipboard()
        # UTF-16 LE 编码，末尾追加 NUL 终止符
        data_bytes = (text + "\0").encode("utf-16-le")
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data_bytes))
        if not h_global:
            return False
        locked = kernel32.GlobalLock(h_global)
        if not locked:
            kernel32.GlobalFree(h_global)
            return False
        ctypes.memmove(locked, data_bytes, len(data_bytes))
        kernel32.GlobalUnlock(h_global)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
            kernel32.GlobalFree(h_global)
            return False
    finally:
        user32.CloseClipboard()
    return True

def print_ai_prompt():
    """输出供用户复制给AI的书签生成提示词，并写入剪贴板"""
    print("\n" + "-" * 50)
    print("将以下提示词及书籍目录截图提供给AI，用于生成书签内容：")
    print("-" * 50)
    print("\n\n" + AI_PROMPT)
    print("-" * 50)
    if copy_to_clipboard(AI_PROMPT):
        print("\n提示词已复制到剪贴板，可直接粘贴给AI。")
    else:
        print("\n[警告] 剪贴板写入失败，请手动复制上方提示词。")

def parse_bookmarks():
    """解析用户输入的书签内容"""
    print("\n\n注意：无需手动计算目录偏移，后续将另行计算\n\n请输入遵守格式的书签内容（回车两次结束）：")
    bookmarks = []
    while True:
        raw = input()
        # 行首「...」标记为二级项，去掉标记后按一级项处理
        if raw.startswith('...'):
            level = 2
            raw = raw[3:]
        else:
            level = 1
        line = raw.strip()
        # 跳过纯空行
        if not line:
            break
        # 兼容-前后任意空格、前导多余符号/空格，精准匹配「数字-标题」格式
        match = re.match(r'^\D*(\d+)\s*-\s*(.+)$', line)
        if not match:
            print(f"[警告] 已跳过格式错误行: {line}")
            continue

        page_part, title = match.groups()
        title = title.strip()
        try:
            # 自动处理前导零的页码
            page_num = int(page_part) - 1
            if page_num < 0:
                raise ValueError
            bookmarks.append((title, page_num, level))
        except ValueError:
            print(f"[警告] 已跳过页码错误行: {line}")
    return bookmarks

def get_page_offset(pdf_path, bookmarks):
    """打开PDF，询问第一项实际页码，换算并返回页码偏移量"""
    first_title, first_page_num, _ = bookmarks[0]
    printed_page = first_page_num + 1  # 转为1-based自然页码
    # 打开PDF供用户查看实际页码
    try:
        os.startfile(pdf_path)
    except Exception:
        print(f"(无法自动打开PDF，请手动打开查看: {pdf_path})")
    print(f"\n第一项「{first_title}」在目录中标注为第 {printed_page} 页。")
    while True:
        raw = input("请输入它在PDF中的实际页码: ").strip()
        try:
            actual_page = int(raw)
            if actual_page < 1:
                print("[错误] 页码必须为正整数，请重新输入。")
                continue
            offset = actual_page - printed_page
            if offset != 0:
                sign = '+' if offset > 0 else ''
                print(f"所有目录项页码已偏移 {sign}{offset}。")
            return offset
        except ValueError:
            print("[错误] 输入无效，请输入数字页码。")

def add_bookmarks(pdf_path, bookmarks):
    """添加书签并保存新PDF（适配pypdf 3.x版本）"""
    # 生成新文件名
    directory, filename = os.path.split(pdf_path)
    name, ext = os.path.splitext(filename)
    new_path = os.path.join(directory, f"{name}-带书签{ext}")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # 复制所有页面到writer
    for page in reader.pages:
        writer.add_page(page)

    # 添加书签：支持二级嵌套
    current_parent = None
    for title, page_num, level in bookmarks:
        if page_num < 0 or page_num >= len(reader.pages):
            print(f"[警告] 已跳过超出范围的书签: {title} (页码:{page_num+1})")
            # 一级项被跳过时重置父节点，避免后续二级项错挂到前一个一级项下
            if level == 1:
                current_parent = None
            continue
        if level == 1:
            # 一级项：作为后续二级项的父节点
            current_parent = writer.add_outline_item(title, page_num)
        else:
            # 二级项：挂到最近的一级项下；若无父项则落到根级
            writer.add_outline_item(title, page_num, parent=current_parent)

    # 保存文件
    with open(new_path, 'wb') as f:
        writer.write(f)
    print(f"\n[成功] 新文件已保存至:\n{new_path}")
    # 自动打开处理完的PDF
    try:
        os.startfile(new_path)
    except Exception:
        print(f"(无法自动打开，请手动查看: {new_path})")

if __name__ == "__main__":
    print("=== PDF 书签添加器 ===")
    pdf_path = get_valid_pdf_path()
    print_ai_prompt()
    bookmarks = parse_bookmarks()

    if bookmarks:
        offset = get_page_offset(pdf_path, bookmarks)
        bookmarks = [(t, p + offset, lvl) for t, p, lvl in bookmarks]
        add_bookmarks(pdf_path, bookmarks)
    else:
        print("[错误] 未输入有效书签，程序结束。")
    input("\n按回车键退出...")
