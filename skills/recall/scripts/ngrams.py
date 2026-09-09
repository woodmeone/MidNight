"""CJK 友好的字面 n-gram（unigram + bigram）——倒排索引的原子单位。

用于 T4 候选预筛：ingest 时把每个 chunk 正文的词面 n-gram 写入 `chunk_ngrams`
倒排表；召回时按查询的 n-gram 找出"可能相关"的一小摞 chunk，再去向量精排。

之所以不直接用 SQLite FTS5 trigram：trigram 要求 ≥3 字符，而中文查询常常很
短（如「张娜」「升学」= 2 字），匹配会落空。这里用 unigram+bigram，既能覆盖
2 字查询，又与嵌入模型的字符特征口径一致。
"""


def content_ngrams(text: str) -> set:
    """去空白后取字符 unigram + bigram 的集合。中文/英文混排皆适用。"""
    chars = [c for c in (text or '') if not c.isspace()]
    grams = set()
    for i in range(len(chars)):
        grams.add(chars[i])
        if i + 1 < len(chars):
            grams.add(chars[i] + chars[i + 1])
    return grams


def candidate_grams(text: str) -> list:
    """预筛用的候选 gram：优先 bigram（更特异、少误命中）；无 bigram 才退回全量。"""
    grams = content_ngrams(text or '')
    bigrams = [g for g in grams if len(g) == 2]
    return bigrams if bigrams else list(grams)