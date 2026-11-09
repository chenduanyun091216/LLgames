"""剥离 PNG 的 iCCP 块（消除 libpng 的 "iCCP: known incorrect sRGB profile" 警告）。

无损操作：只移除 iCCP chunk，其余 chunk（含 IDAT 像素数据）原样保留。
用法：python3 scripts/strip_png_icc.py [目录，默认 assets/images]
"""
import os
import struct
import sys

PNG_SIG = b'\x89PNG\r\n\x1a\n'


def strip_icc(path):
    """从单个 PNG 中移除 iCCP chunk，返回是否发生了修改。"""
    with open(path, 'rb') as f:
        data = f.read()
    if data[:8] != PNG_SIG:
        return False
    out = bytearray(PNG_SIG)
    pos = 8
    changed = False
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos:pos + 12 + length]
        if ctype == b'iCCP':
            changed = True
        else:
            out += chunk
        pos += 12 + length
    if changed:
        with open(path, 'wb') as f:
            f.write(bytes(out))
    return changed


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'images')
    fixed, total = 0, 0
    for name in sorted(os.listdir(target_dir)):
        if not name.endswith('.png'):
            continue
        total += 1
        path = os.path.join(target_dir, name)
        if strip_icc(path):
            fixed += 1
            print(f'  清理 {name}')
    print(f'完成：{total} 个 PNG，剥离 iCCP {fixed} 个')


if __name__ == '__main__':
    main()
