namespace Thoughtbench.Core.Modeling;

public sealed record GenerationOptions(
    int MaxTokens = 2048,
    double Temperature = 1.0,
    double TopP = 0.95,
    int TopK = 64,
    bool ThinkingEnabled = false);
