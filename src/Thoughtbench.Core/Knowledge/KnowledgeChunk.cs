namespace Thoughtbench.Core.Knowledge;

public sealed record KnowledgeChunk(string ChunkId, string Source, string Text);

public sealed record KnowledgeResult(KnowledgeChunk Chunk, double Score, string[] MatchedTerms)
{
    public int MatchedTermCount => MatchedTerms.Length;
}
