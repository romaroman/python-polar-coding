import numpy as np

from ..base import functions
from .fast_ssc_decoder import FastSSCDecoder, FastSSCNode


def splits(start, end):
    while start <= end:
        yield start
        start *= 2


class GeneralizedFastSSCNode(FastSSCNode):
    """Decoder for Generalized Fast SSC code.

    Based on: https://arxiv.org/pdf/1804.09508.pdf

    """
    G_REPETITION = 'G-REPETITION'
    RG_PARITY = 'RG-PARITY'

    MIN_CHUNKS = 2

    def __init__(self, AF=1, *args, **kwargs):
        self.AF = AF
        self.last_chunk_type = None
        self.mask_steps = None
        super().__init__(*args, **kwargs)

    def get_node_type(self):
        ntype = super().get_node_type()
        if ntype != self.OTHER:
            return ntype
        if self._check_is_g_repetition():
            return self.G_REPETITION
        if self._check_is_rg_parity():
            return self.RG_PARITY
        return self.OTHER

    def _build_decoding_tree(self):
        """Build Generalized Fast SSC decoding tree."""
        if self.is_simplified_node:
            return

        if self._mask.size == self.M:
            return

        left_mask, right_mask = np.split(self._mask, 2)
        cls = self.__class__
        cls(mask=left_mask, name=self.LEFT, N_min=self.M, parent=self, AF=self.AF)
        cls(mask=right_mask, name=self.RIGHT, N_min=self.M, parent=self, AF=self.AF)

    def _check_is_g_repetition(self):
        """Check the node is Generalized Repetition node.

        Based on: https://arxiv.org/pdf/1804.09508.pdf, Section III, A.

        """
        # 1. Split mask into T chunks, T in range [2, 4, ..., N/2]
        for t in splits(self.MIN_CHUNKS, self.N // 2):
            chunks = np.split(self._mask, t)

            last = chunks[-1]
            last_ok = (
                (self._check_is_spc(last) and last.size >= self.REPETITION_MIN_SIZE)
                or self._check_is_one(last)
            )
            if not last_ok:
                continue

            others_ok = all(self._check_is_zero(c) for c in chunks[:-1])
            if not others_ok:
                continue

            self.last_chunk_type = 1 if self._check_is_one(last) else 0
            self.mask_steps = t
            return True

        return False

    def _check_is_rg_parity(self):
        """Check the node is Relaxed Generalized Parity Check node.

        Based on: https://arxiv.org/pdf/1804.09508.pdf, Section III, B.

        """
        # 1. Split mask into T chunks, T in range [2, 4, ..., N/2]
        for t in splits(self.MIN_CHUNKS, self.N // 2):
            chunks = np.split(self._mask, t)

            first = chunks[0]
            if not self._check_is_zero(first):
                continue

            ones = 0
            spcs = 0
            for c in chunks[1:]:
                if self._check_is_one(c):
                    ones += 1
                elif c.size >= self.SPC_MIN_SIZE and self._check_is_spc(c):
                    spcs += 1

            others_ok = (ones + spcs + 1) == t and spcs <= self.AF
            if not others_ok:
                continue

            self.mask_steps = t
            return True

        return False

    def compute_leaf_beta(self):
        super().compute_leaf_beta()
        klass = self.__class__

        if self._node_type == klass.G_REPETITION:
            self._beta = functions.compute_g_repetition(
                llr=self.alpha,
                mask_steps=self.mask_steps,
                last_chunk_type=self.last_chunk_type,
                N=self.N,
            )
        if self._node_type == klass.RG_PARITY:
            self._beta = functions.compute_rg_parity(
                llr=self.alpha,
                mask_steps=self.mask_steps,
                N=self.N,
            )


class GeneralizedFastSSCDecoder(FastSSCDecoder):
    node_class = GeneralizedFastSSCNode

    def __init__(self, n: int,
                 mask: np.array,
                 is_systematic: bool = True,
                 code_min_size: int = 0,
                 AF: int = 1):
        super().__init__(n=n, mask=mask, is_systematic=is_systematic)
        self._decoding_tree = self.node_class(mask=self.mask,
                                              N_min=code_min_size,
                                              AF=AF)
        self._position = 0