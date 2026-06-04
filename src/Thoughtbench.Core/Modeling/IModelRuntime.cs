namespace Thoughtbench.Core.Modeling;

public interface IModelRuntime
{
    Task LoadAsync(ModelSelection selection, CancellationToken cancellationToken);

    Task<string> GenerateAsync(
        IReadOnlyList<ChatMessage> messages,
        GenerationOptions options,
        IProgress<GenerationChunk> progress,
        CancellationToken cancellationToken);

    Task<int> CountTokensAsync(
        IReadOnlyList<ChatMessage> messages,
        GenerationOptions options,
        CancellationToken cancellationToken);

    int GetContextLimit();
}
