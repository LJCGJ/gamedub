"""
Descompressão LZO1X.

Usa `lzallright` (Rust, com wheels prontos) quando disponível; caso
contrário cai num descompressor em Python puro, mais lento mas sem
dependência de compilador. O pacote `python-lzo` foi descartado porque
exige compilar a liblzo no Windows.
"""
from __future__ import annotations

try:
    from lzallright import LZOCompressor as _LZO
except ImportError:  # pragma: no cover
    _LZO = None


def decompress(src: bytes, out_len: int) -> bytes:
    if _LZO is not None:
        return bytes(_LZO.decompress(src, output_size_hint=out_len))
    return _decompress_py(src, out_len)


def _decompress_py(src: bytes, out_len: int) -> bytes:
    """Port direto do lzo1x_decompress de referência (sem checagens de limite)."""
    out = bytearray(out_len)
    ip = 0
    op = 0
    n = len(src)

    def copy_literals(cnt):
        nonlocal ip, op
        out[op:op + cnt] = src[ip:ip + cnt]
        ip += cnt
        op += cnt

    def copy_match(m_pos, cnt):
        nonlocal op
        if m_pos + cnt <= op:            # sem sobreposição: cópia em bloco
            out[op:op + cnt] = out[m_pos:m_pos + cnt]
            op += cnt
        else:
            for _ in range(cnt):
                out[op] = out[m_pos]
                op += 1
                m_pos += 1

    t = src[ip]
    state = "top"
    if t > 17:
        ip += 1
        t -= 17
        if t < 4:
            state = "match_next"
        else:
            copy_literals(t)
            state = "first_literal_run"

    while ip < n:
        if state == "top":
            t = src[ip]; ip += 1
            if t >= 16:
                state = "match"
                continue
            if t == 0:
                while src[ip] == 0:
                    t += 255; ip += 1
                t += 15 + src[ip]; ip += 1
            copy_literals(t + 3)
            state = "first_literal_run"
            continue

        if state == "first_literal_run":
            t = src[ip]; ip += 1
            if t >= 16:
                state = "match"
                continue
            m_pos = op - (1 + 0x0800) - (t >> 2) - (src[ip] << 2); ip += 1
            copy_match(m_pos, 3)
            state = "match_done"
            continue

        if state == "match":
            if t >= 64:
                m_pos = op - 1 - ((t >> 2) & 7) - (src[ip] << 3); ip += 1
                t = (t >> 5) - 1
                copy_match(m_pos, t + 2)
            elif t >= 32:
                t &= 31
                if t == 0:
                    while src[ip] == 0:
                        t += 255; ip += 1
                    t += 31 + src[ip]; ip += 1
                m_pos = op - 1 - ((src[ip] >> 2) + (src[ip + 1] << 6)); ip += 2
                copy_match(m_pos, t + 2)
            elif t >= 16:
                m_pos = op - ((t & 8) << 11)
                t &= 7
                if t == 0:
                    while src[ip] == 0:
                        t += 255; ip += 1
                    t += 7 + src[ip]; ip += 1
                m_pos -= (src[ip] >> 2) + (src[ip + 1] << 6); ip += 2
                if m_pos == op:
                    break                      # marcador de fim
                m_pos -= 0x4000
                copy_match(m_pos, t + 2)
            else:
                m_pos = op - 1 - (t >> 2) - (src[ip] << 2); ip += 1
                copy_match(m_pos, 2)
            state = "match_done"
            continue

        if state == "match_done":
            t = src[ip - 2] & 3
            if t == 0:
                state = "top"
            else:
                state = "match_next"
            continue

        if state == "match_next":
            copy_literals(t)
            t = src[ip]; ip += 1
            state = "match"
            continue

    return bytes(out[:op])
