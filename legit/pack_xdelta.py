from legit.pack import MAX_COPY_SIZE, MAX_INSERT_SIZE
from collections import defaultdict


class XDelta:
    BLOCK_SIZE = 16

    def __init__(self, source, index):
        self.source = source
        self.index = index

    @staticmethod
    def create_index(source):
        blocks = len(source) / XDelta.BLOCK_SIZE
        index = defaultdict(list)

        for i in range(int(blocks)):
            offset = i * XDelta.BLOCK_SIZE
            _slice = source[offset : offset + XDelta.BLOCK_SIZE]

            index[_slice].append(offset)

        return XDelta(source, index)

    def compress(self, target):
        self.target = target
        self.offset = 0
        self.insert = []
        self.ops = []

        while self.offset < len(self.target):
            self.generate_ops()

        self.flush_insert()

        return self.ops

    def generate_ops(self):
        from legit.pack_delta import Delta

        m_offset, m_size = self.longest_match()
        if m_size == 0:
            return self.push_insert()

        m_offset, m_size = self.expand_match(m_offset, m_size)

        self.flush_insert()
        self.ops.append(Delta.Copy(m_offset, m_size))

    def longest_match(self):
        _slice = self.target[self.offset : self.offset + XDelta.BLOCK_SIZE]
        if _slice not in self.index:
            return [0, 0]

        m_offset = m_size = 0

        for pos in self.index[_slice]:
            remaining = self.remaining_bytes(pos)
            if remaining <= m_size:
                break

            s = self.match_from(pos, remaining)
            if m_size >= s - pos:
                continue

            m_offset = pos
            m_size = s - pos

        return [m_offset, m_size]

    def remaining_bytes(self, pos):
        source_remaining = len(self.source) - pos
        target_remaining = len(self.target) - self.offset

        return min(source_remaining, target_remaining, MAX_COPY_SIZE)

    def match_from(self, pos, remaining):
        s, t = pos, self.offset

        while remaining > 0 and self.source[s] == self.target[t]:
            s, t = s + 1, t + 1
            remaining -= 1

        return s

    def expand_match(self, m_offset, m_size):
        while (
            self.insert
            and m_offset > 0
            and self.source[m_offset - 1] == self.insert[-1]
        ):
            if m_size == MAX_COPY_SIZE:
                break

            self.offset -= 1
            m_offset -= 1
            m_size += 1

            self.insert.pop()

        self.offset += m_size
        return [m_offset, m_size]

    def push_insert(self):
        self.insert.append(self.target[self.offset])
        self.offset += 1
        self.flush_insert(MAX_INSERT_SIZE)

    def flush_insert(self, size=None):
        from legit.pack_delta import Delta

        if size and len(self.insert) < size:
            return
        if not self.insert:
            return

        self.ops.append(Delta.Insert(bytes(self.insert)))
        self.insert = []
