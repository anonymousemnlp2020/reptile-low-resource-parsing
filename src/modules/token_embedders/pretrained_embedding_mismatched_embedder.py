from typing import Optional

from overrides import overrides
import torch

from allennlp.modules.token_embedders import TokenEmbedder
from allennlp.modules import Seq2SeqEncoder
from allennlp.nn import util

from src.modules.token_embedders import PretrainedEmbeddingEmbedder


@TokenEmbedder.register("pretrained_embedding_mismatched")
class PretrainedEmbeddingMismatchedEmbedder(TokenEmbedder):
    """
    Use this embedder to embed wordpieces given by `PretrainedTransformerMismatchedIndexer`
    and to pool the resulting vectors to get word-level representations.

    # Parameters

    pretrained_file : `str`
        The file path the embedding to use.
    encoder: `Seq2SeqEncoder`, optional (default = None)
        An encoder that takes wordpiece-level representations as input, later being
        averaged to produce word-level representations.
    trainable: `bool`, optional (default = True)
        Whether the embedding is trainable.
    """

    def __init__(
        self,
        pretrained_file: str,
        encoder: Seq2SeqEncoder = None,
        trainable: bool = True,
        ) -> None:
        super().__init__()
        # The matched version v.s. mismatched
        self._matched_embedder = PretrainedEmbeddingEmbedder(
            pretrained_file,
            encoder,
            trainable,
        )

    @overrides
    def get_output_dim(self):
        return self._matched_embedder.get_output_dim()

    @overrides
    def forward(
        self,
        token_ids: torch.LongTensor,
        mask: torch.LongTensor,
        offsets: torch.LongTensor,
        wordpiece_mask: torch.LongTensor,
        type_ids: Optional[torch.LongTensor] = None,
        segment_concat_mask: Optional[torch.LongTensor] = None,
    ) -> torch.Tensor:  # type: ignore
        """
        # Parameters

        token_ids: torch.LongTensor
            Shape: [batch_size, num_wordpieces] (for exception see `PretrainedTransformerEmbedder`).
        mask: torch.LongTensor
            Shape: [batch_size, num_orig_tokens].
        offsets: torch.LongTensor
            Shape: [batch_size, num_orig_tokens, 2].
            Maps indices for the original tokens, i.e. those given as input to the indexer,
            to a span in token_ids. `token_ids[i][offsets[i][j][0]:offsets[i][j][1] + 1]`
            corresponds to the original j-th token from the i-th batch.
        wordpiece_mask: torch.LongTensor
            Shape: [batch_size, num_wordpieces].
        type_ids: Optional[torch.LongTensor]
            Shape: [batch_size, num_wordpieces].
        segment_concat_mask: Optional[torch.LongTensor]
            See `PretrainedTransformerEmbedder`.

        # Returns:

        Shape: [batch_size, num_orig_tokens, embedding_size].
        """
        # Shape: [batch_size, num_wordpieces, embedding_size].
        embeddings = self._matched_embedder(
            token_ids, wordpiece_mask, type_ids=type_ids, segment_concat_mask=segment_concat_mask
        )

        # span_embeddings: (batch_size, num_orig_tokens, max_span_length, embedding_size)
        # span_mask: (batch_size, num_orig_tokens, max_span_length)
        span_embeddings, span_mask = util.batched_span_select(embeddings.contiguous(), offsets)
        span_mask = span_mask.unsqueeze(-1)
        span_embeddings *= span_mask  # zero out paddings

        span_embeddings_sum = span_embeddings.sum(2)
        span_embeddings_len = span_mask.sum(2)
        # Shape: (batch_size, num_orig_tokens, embedding_size)
        orig_embeddings = span_embeddings_sum / span_embeddings_len

        return orig_embeddings
