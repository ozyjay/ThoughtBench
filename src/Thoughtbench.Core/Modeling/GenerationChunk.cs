namespace Thoughtbench.Core.Modeling;

public enum GenerationChannel
{
    Thinking,
    Response,
    System
}

public sealed record GenerationChunk(string Text, GenerationChannel Channel);
