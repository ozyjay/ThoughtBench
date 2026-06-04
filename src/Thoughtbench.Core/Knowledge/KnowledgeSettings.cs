namespace Thoughtbench.Core.Knowledge;

public sealed record KnowledgeSettings(
    int TopK = 6,
    int ContextCharBudget = 6000,
    int ChunkSize = 180,
    int ChunkOverlap = 30,
    double MinimumScore = 0.5,
    int MinimumMatchedTerms = 1)
{
    public static KnowledgeSettings Default { get; } = new();

    public bool IsValid() =>
        TopK > 0 &&
        ContextCharBudget > 0 &&
        ChunkSize > 0 &&
        ChunkOverlap >= 0 &&
        ChunkOverlap < ChunkSize &&
        MinimumScore >= 0 &&
        MinimumMatchedTerms > 0;
}
