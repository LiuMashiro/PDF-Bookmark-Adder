import os
import re
from PyPDF2 import PdfReader, PdfWriter


def get_valid_pdf_path():
    """获取并验证用户输入的PDF路径（自动过滤拖拽产生的引号）"""
    while True:
        path = input("请输入PDF文件路径: ").strip()
        #自动去除路径首尾的双引号、单引号
        path = path.strip('"\'')
        if os.path.isfile(path) and path.lower().endswith('.pdf'):
            return path
        print("❌ 输入错误，请重新输入。")

def print_ai_prompt():
    """输出供用户复制给AI的书签生成提示词"""
    print("\n" + "-" * 50)
    print("以下提示词可复制给AI，用于生成书签内容：")
    print("-" * 50)
    print("将目录整理为页码-标题（如001-第一节 示例标题，每行换行）的格式。"
          "板块、部分、章节、篇章等分节（如有）必须写入目录格式中。"
          "尽量压缩目录名，不要太长。")
    print("示例：")
    print("001-第一板块")
    print("001-第一部分")
    print("001-第一章 第一节 示例1")
    print("007-第二章 第二节 示例2")
    print("008-第二部分")
    print("......")
    print('严禁出现："第一板块..."而非"001-第一板块"等不遵守目录格式的行')
    print("所有页码均+N")
    print("-" * 50)

def parse_bookmarks():
    """解析用户输入的书签内容，兼容全格式、多行粘贴"""
    print("\n请输入遵守格式的书签内容（回车两次结束）：")
    bookmarks = []
    while True:
        line = input().strip()
        # 跳过纯空行
        if not line:
            break
        # 兼容-前后任意空格、前导多余符号/空格，精准匹配「数字-标题」格式
        match = re.match(r'^\D*(\d+)\s*-\s*(.+)$', line)
        if not match:
            print(f"⚠️ 已跳过格式错误行: {line}")
            continue
        
        page_part, title = match.groups()
        try:
            # 自动处理前导零的页码
            page_num = int(page_part) - 1 
            if page_num < 0:
                raise ValueError
            bookmarks.append((title.strip(), page_num))
        except ValueError:
            print(f"⚠️ 已跳过页码错误行: {line}")
    return bookmarks

def add_bookmarks(pdf_path, bookmarks):
    """添加书签并保存新PDF（适配PyPDF2 3.0.0+版本）"""
    # 生成新文件名
    directory, filename = os.path.split(pdf_path)
    name, ext = os.path.splitext(filename)
    new_path = os.path.join(directory, f"{name}-带书签{ext}")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # 复制所有页面到writer
    for page in reader.pages:
        writer.add_page(page)

    # 添加书签：适配新版API
    for title, page_num in bookmarks:
        if page_num < len(reader.pages):
            writer.add_outline_item(title, page_num)
        else:
            print(f"⚠️ 已跳过超出范围的书签: {title} (页码:{page_num+1})")

    # 保存文件
    with open(new_path, 'wb') as f:
        writer.write(f)
    print(f"\n✅ 成功！新文件已保存至:\n{new_path}")

if __name__ == "__main__":
    print("=== PDF 书签添加器 ===")
    pdf_path = get_valid_pdf_path()
    print_ai_prompt()
    bookmarks = parse_bookmarks()
    
    if bookmarks:
        add_bookmarks(pdf_path, bookmarks)
    else:
        print("❌ 未输入有效书签，程序结束。")
